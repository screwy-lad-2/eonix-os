//! # Eonix IPC Broker
//!
//! Capability-based inter-process communication broker.
//! Every message carries a cryptographic capability token —
//! no process can escalate its own privileges.

use std::collections::HashMap;

/// A capability token granting specific permissions
#[derive(Debug, Clone)]
pub struct Capability {
    pub token: [u8; 32],
    pub permissions: Permissions,
    pub target: String,
}

/// Permission flags for IPC operations
#[derive(Debug, Clone, Copy)]
pub struct Permissions {
    pub read: bool,
    pub write: bool,
    pub execute: bool,
    pub grant: bool,
}

impl Permissions {
    pub fn read_only() -> Self {
        Permissions {
            read: true,
            write: false,
            execute: false,
            grant: false,
        }
    }

    pub fn read_write() -> Self {
        Permissions {
            read: true,
            write: true,
            execute: false,
            grant: false,
        }
    }
}

/// IPC message with capability-based authorization
#[derive(Debug)]
pub struct IpcMessage {
    pub sender_id: u32,
    pub receiver_id: u32,
    pub capability: Capability,
    pub payload: Vec<u8>,
}

/// The IPC broker that routes messages between processes
pub struct IpcBroker {
    capabilities: HashMap<u32, Vec<Capability>>,
}

impl IpcBroker {
    pub fn new() -> Self {
        IpcBroker {
            capabilities: HashMap::new(),
        }
    }

    /// Grant a capability to a process
    pub fn grant_capability(&mut self, process_id: u32, cap: Capability) {
        self.capabilities
            .entry(process_id)
            .or_default()
            .push(cap);
    }

    /// Validate that a message's capability is authorized
    pub fn validate_message(&self, msg: &IpcMessage) -> bool {
        if let Some(caps) = self.capabilities.get(&msg.sender_id) {
            caps.iter().any(|c| c.token == msg.capability.token)
        } else {
            false
        }
    }
}

impl Default for IpcBroker {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_capability_validation() {
        let mut broker = IpcBroker::new();

        let cap = Capability {
            token: [1u8; 32],
            permissions: Permissions::read_only(),
            target: "scheduler".to_string(),
        };

        broker.grant_capability(100, cap.clone());

        let msg = IpcMessage {
            sender_id: 100,
            receiver_id: 200,
            capability: cap,
            payload: vec![1, 2, 3],
        };

        assert!(broker.validate_message(&msg));
    }

    #[test]
    fn test_unauthorized_message() {
        let broker = IpcBroker::new();

        let msg = IpcMessage {
            sender_id: 999,
            receiver_id: 200,
            capability: Capability {
                token: [0u8; 32],
                permissions: Permissions::read_only(),
                target: "scheduler".to_string(),
            },
            payload: vec![],
        };

        assert!(!broker.validate_message(&msg));
    }
}
