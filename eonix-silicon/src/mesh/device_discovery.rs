//! # Eonix Silicon — Device Mesh Discovery
//!
//! Provides mDNS-style device discovery for the Eonix device mesh.

use std::collections::HashMap;
use std::net::IpAddr;

// ───────── Device Types ─────────

/// Type of device on the mesh.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum DeviceType {
    Laptop,
    Desktop,
    Phone,
    Tablet,
}

impl std::fmt::Display for DeviceType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DeviceType::Laptop => write!(f, "Laptop"),
            DeviceType::Desktop => write!(f, "Desktop"),
            DeviceType::Phone => write!(f, "Phone"),
            DeviceType::Tablet => write!(f, "Tablet"),
        }
    }
}

// ───────── Eonix Device ─────────

/// A device discovered on the Eonix mesh network.
#[derive(Debug, Clone)]
pub struct EonixDevice {
    pub device_id: String,
    pub device_name: String,
    pub device_type: DeviceType,
    pub ip_address: IpAddr,
    pub port: u16,
    pub last_seen: u64,
}

impl EonixDevice {
    pub fn new(
        device_id: String,
        device_name: String,
        device_type: DeviceType,
        ip_address: IpAddr,
        last_seen: u64,
    ) -> Self {
        EonixDevice {
            device_id,
            device_name,
            device_type,
            ip_address,
            port: 8765,
            last_seen,
        }
    }
}

// ───────── Device Mesh ─────────

/// Manages a set of known Eonix devices.
pub struct DeviceMesh {
    known_devices: HashMap<String, EonixDevice>,
}

impl DeviceMesh {
    pub fn new() -> Self {
        DeviceMesh {
            known_devices: HashMap::new(),
        }
    }

    /// Generate mDNS-style announcement string.
    pub fn announce(device: &EonixDevice) -> String {
        format!(
            "EONIX_ANNOUNCE device_id={} name={} type={} ip={} port={}",
            device.device_id, device.device_name, device.device_type,
            device.ip_address, device.port,
        )
    }

    /// Discover all known devices (stub: returns internal list).
    pub fn discover(&self) -> Vec<&EonixDevice> {
        self.known_devices.values().collect()
    }

    /// Add a device to the mesh.
    pub fn add_device(&mut self, device: EonixDevice) {
        self.known_devices
            .insert(device.device_id.clone(), device);
    }

    /// Remove a device from the mesh by ID.
    pub fn remove_device(&mut self, device_id: &str) -> bool {
        self.known_devices.remove(device_id).is_some()
    }

    /// Look up a device by ID.
    pub fn get_device(&self, device_id: &str) -> Option<&EonixDevice> {
        self.known_devices.get(device_id)
    }

    /// Number of known devices.
    pub fn count(&self) -> usize {
        self.known_devices.len()
    }
}

impl Default for DeviceMesh {
    fn default() -> Self {
        Self::new()
    }
}

// ───────── Tests ─────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv4Addr;

    fn make_device(id: &str, name: &str) -> EonixDevice {
        EonixDevice::new(
            id.to_string(),
            name.to_string(),
            DeviceType::Laptop,
            IpAddr::V4(Ipv4Addr::new(192, 168, 1, 100)),
            1710000000,
        )
    }

    #[test]
    fn test_add_and_retrieve_device() {
        let mut mesh = DeviceMesh::new();
        let device = make_device("abc-123", "MyLaptop");
        mesh.add_device(device);

        assert_eq!(mesh.count(), 1);
        let retrieved = mesh.get_device("abc-123").unwrap();
        assert_eq!(retrieved.device_name, "MyLaptop");
        assert_eq!(retrieved.port, 8765);
    }

    #[test]
    fn test_remove_device() {
        let mut mesh = DeviceMesh::new();
        mesh.add_device(make_device("dev-1", "Device1"));
        mesh.add_device(make_device("dev-2", "Device2"));
        assert_eq!(mesh.count(), 2);

        assert!(mesh.remove_device("dev-1"));
        assert_eq!(mesh.count(), 1);
        assert!(mesh.get_device("dev-1").is_none());
        assert!(mesh.get_device("dev-2").is_some());

        // Removing non-existent returns false
        assert!(!mesh.remove_device("dev-999"));
    }

    #[test]
    fn test_announce_format() {
        let device = make_device("uuid-4567", "WorkPC");
        let announcement = DeviceMesh::announce(&device);

        assert!(announcement.starts_with("EONIX_ANNOUNCE"));
        assert!(announcement.contains("device_id=uuid-4567"));
        assert!(announcement.contains("name=WorkPC"));
        assert!(announcement.contains("type=Laptop"));
        assert!(announcement.contains("ip=192.168.1.100"));
        assert!(announcement.contains("port=8765"));
    }
}
