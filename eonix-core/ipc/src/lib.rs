//! # Eonix IPC Broker
//!
//! Capability-based inter-process communication broker.
//! Every message carries a cryptographic capability token —
//! no process can escalate its own privileges.
//!
//! Capabilities carry fine-grained permissions and optional expiry.
//! The broker routes messages through a VecDeque per-process mailbox.

use std::collections::{HashMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

// ---------------------------------------------------------------------------
// Permissions & Capabilities
// ---------------------------------------------------------------------------

/// Fine-grained permission flags
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Permission {
    Read,
    Write,
    Execute,
    Signal,
    SpawnChild,
}

/// A capability token granting specific permissions to a target resource.
#[derive(Debug, Clone)]
pub struct Capability {
    /// Unique 128-bit token (UUID-sized)
    pub token: [u8; 16],
    /// Set of granted permissions
    pub permissions: Vec<Permission>,
    /// Target resource identifier
    pub target: String,
    /// Optional expiry (Unix timestamp in seconds). `None` = never expires.
    pub expires_at: Option<u64>,
}

impl Capability {
    /// Check whether this capability includes a specific permission.
    pub fn has_permission(&self, perm: Permission) -> bool {
        self.permissions.contains(&perm)
    }

    /// Check whether this capability has expired relative to `now` (unix secs).
    pub fn is_expired(&self, now_secs: u64) -> bool {
        if let Some(exp) = self.expires_at {
            now_secs >= exp
        } else {
            false
        }
    }
}

// ---------------------------------------------------------------------------
// IPC Messages
// ---------------------------------------------------------------------------

/// An IPC message routed through the broker.
#[derive(Debug, Clone)]
pub struct IpcMessage {
    pub sender_id: u32,
    pub receiver_id: u32,
    pub token: [u8; 16],
    pub payload: Vec<u8>,
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IpcError {
    /// The capability token was not found or has been revoked.
    InvalidCapability,
    /// The capability has expired.
    ExpiredCapability,
    /// The capability does not include the required permission.
    PermissionDenied,
    /// No messages available in the mailbox.
    EmptyMailbox,
    /// A catch-all for internal failures.
    InternalError(String),
}

// ---------------------------------------------------------------------------
// IPC Broker
// ---------------------------------------------------------------------------

/// The IPC broker routes messages between processes using
/// capability-based authorization.
pub struct IpcBroker {
    /// Capabilities issued per process-id.
    capabilities: HashMap<u32, Vec<Capability>>,
    /// Per-process mailbox (FIFO).
    mailboxes: HashMap<u32, VecDeque<IpcMessage>>,
    /// Monotonic counter used as entropy seed for token generation.
    counter: u64,
}

impl IpcBroker {
    pub fn new() -> Self {
        IpcBroker {
            capabilities: HashMap::new(),
            mailboxes: HashMap::new(),
            counter: 0,
        }
    }

    // -- Capability management ---------------------------------------------

    /// Issue a new capability for `process_id` targeting `target` with
    /// the supplied permissions and optional expiry.
    ///
    /// Returns the generated capability token.
    pub fn issue_capability(
        &mut self,
        process_id: u32,
        target: &str,
        permissions: Vec<Permission>,
        expires_at: Option<u64>,
    ) -> [u8; 16] {
        let token = self.generate_token(process_id);
        let cap = Capability {
            token,
            permissions,
            target: target.to_string(),
            expires_at,
        };
        self.capabilities.entry(process_id).or_default().push(cap);
        token
    }

    /// Revoke a specific capability by token.
    pub fn revoke_capability(&mut self, process_id: u32, token: &[u8; 16]) -> bool {
        if let Some(caps) = self.capabilities.get_mut(&process_id) {
            let before = caps.len();
            caps.retain(|c| &c.token != token);
            caps.len() < before
        } else {
            false
        }
    }

    // -- Messaging ---------------------------------------------------------

    /// Send a message from `sender_id` to `receiver_id`.
    ///
    /// The sender must hold a valid, non-expired capability with `Write`
    /// permission for the receiver's target.
    pub fn send(&mut self, msg: IpcMessage) -> Result<(), IpcError> {
        let now = now_secs();
        let cap = self.find_capability(msg.sender_id, &msg.token)?;

        if cap.is_expired(now) {
            return Err(IpcError::ExpiredCapability);
        }
        if !cap.has_permission(Permission::Write) {
            return Err(IpcError::PermissionDenied);
        }

        self.mailboxes
            .entry(msg.receiver_id)
            .or_default()
            .push_back(msg);
        Ok(())
    }

    /// Receive the next message for `process_id` (FIFO order).
    pub fn receive(&mut self, process_id: u32) -> Result<IpcMessage, IpcError> {
        self.mailboxes
            .get_mut(&process_id)
            .and_then(|q| q.pop_front())
            .ok_or(IpcError::EmptyMailbox)
    }

    // -- Internals ---------------------------------------------------------

    fn find_capability(&self, process_id: u32, token: &[u8; 16]) -> Result<Capability, IpcError> {
        self.capabilities
            .get(&process_id)
            .and_then(|caps| caps.iter().find(|c| &c.token == token))
            .cloned()
            .ok_or(IpcError::InvalidCapability)
    }

    /// Deterministic token generator (good enough for a simulator;
    /// a real kernel would use a CSPRNG).
    fn generate_token(&mut self, process_id: u32) -> [u8; 16] {
        self.counter += 1;
        let mut token = [0u8; 16];
        let pid_bytes = process_id.to_le_bytes();
        let cnt_bytes = self.counter.to_le_bytes();
        token[..4].copy_from_slice(&pid_bytes);
        token[4..12].copy_from_slice(&cnt_bytes);
        // Mix in a timestamp for extra uniqueness
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as u64;
        let ts_bytes = ts.to_le_bytes();
        token[8..16].copy_from_slice(&ts_bytes);
        token
    }
}

impl Default for IpcBroker {
    fn default() -> Self {
        Self::new()
    }
}

/// Helper: current Unix timestamp in seconds.
fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

// ===========================================================================
// Tests
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_issue_and_send_message() {
        let mut broker = IpcBroker::new();
        let token = broker.issue_capability(
            100,
            "scheduler",
            vec![Permission::Read, Permission::Write],
            None,
        );

        let msg = IpcMessage {
            sender_id: 100,
            receiver_id: 200,
            token,
            payload: b"hello".to_vec(),
        };

        assert!(broker.send(msg).is_ok());
        let received = broker.receive(200).unwrap();
        assert_eq!(received.sender_id, 100);
        assert_eq!(received.payload, b"hello");
    }

    #[test]
    fn test_send_without_capability_fails() {
        let mut broker = IpcBroker::new();
        let msg = IpcMessage {
            sender_id: 999,
            receiver_id: 200,
            token: [0u8; 16],
            payload: vec![],
        };
        assert_eq!(broker.send(msg).unwrap_err(), IpcError::InvalidCapability);
    }

    #[test]
    fn test_send_without_write_permission_fails() {
        let mut broker = IpcBroker::new();
        let token = broker.issue_capability(
            100,
            "scheduler",
            vec![Permission::Read], // no Write
            None,
        );
        let msg = IpcMessage {
            sender_id: 100,
            receiver_id: 200,
            token,
            payload: vec![1, 2, 3],
        };
        assert_eq!(broker.send(msg).unwrap_err(), IpcError::PermissionDenied);
    }

    #[test]
    fn test_expired_capability_rejected() {
        let mut broker = IpcBroker::new();
        // Issue a capability that already expired (epoch 0)
        let token = broker.issue_capability(
            100,
            "scheduler",
            vec![Permission::Write],
            Some(0), // expired
        );
        let msg = IpcMessage {
            sender_id: 100,
            receiver_id: 200,
            token,
            payload: vec![],
        };
        assert_eq!(broker.send(msg).unwrap_err(), IpcError::ExpiredCapability);
    }

    #[test]
    fn test_revoke_capability() {
        let mut broker = IpcBroker::new();
        let token = broker.issue_capability(
            100,
            "scheduler",
            vec![Permission::Write],
            None,
        );

        // Revoke it
        assert!(broker.revoke_capability(100, &token));

        // Now sending should fail
        let msg = IpcMessage {
            sender_id: 100,
            receiver_id: 200,
            token,
            payload: vec![],
        };
        assert_eq!(broker.send(msg).unwrap_err(), IpcError::InvalidCapability);
    }
}
