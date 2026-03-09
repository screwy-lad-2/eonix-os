//! # Eonix Silicon — Driver Registry
//!
//! Manages named HAL device drivers with bulk initialize/shutdown.

use std::collections::HashMap;

use crate::hal::{DeviceStatus, HalDevice, HalError};

// ───────── Driver Registry ─────────

/// Central registry of all HAL device drivers.
pub struct DriverRegistry {
    drivers: HashMap<&'static str, Box<dyn HalDevice>>,
}

impl DriverRegistry {
    pub fn new() -> Self {
        DriverRegistry {
            drivers: HashMap::new(),
        }
    }

    /// Register a named device driver.
    pub fn register(&mut self, name: &'static str, device: Box<dyn HalDevice>) {
        self.drivers.insert(name, device);
    }

    /// Retrieve a driver by name.
    pub fn get(&self, name: &str) -> Option<&dyn HalDevice> {
        self.drivers.get(name).map(|d| d.as_ref())
    }

    /// Initialize all registered drivers. Stops on first error.
    pub fn initialize_all(&mut self) -> Result<(), HalError> {
        for (_name, driver) in self.drivers.iter_mut() {
            driver.initialize()?;
        }
        Ok(())
    }

    /// Shut down all registered drivers. Stops on first error.
    pub fn shutdown_all(&mut self) -> Result<(), HalError> {
        for (_name, driver) in self.drivers.iter_mut() {
            driver.shutdown()?;
        }
        Ok(())
    }

    /// Number of registered drivers.
    pub fn count(&self) -> usize {
        self.drivers.len()
    }
}

impl Default for DriverRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ───────── Stub Drivers ─────────

/// Stub CPU driver.
pub struct CpuDriver {
    status: DeviceStatus,
}

impl CpuDriver {
    pub fn new() -> Self {
        CpuDriver {
            status: DeviceStatus::Uninitialized,
        }
    }
}

impl HalDevice for CpuDriver {
    fn initialize(&mut self) -> Result<(), HalError> {
        self.status = DeviceStatus::Active;
        Ok(())
    }
    fn shutdown(&mut self) -> Result<(), HalError> {
        self.status = DeviceStatus::Suspended;
        Ok(())
    }
    fn status(&self) -> DeviceStatus {
        self.status
    }
}

/// Stub Memory driver.
pub struct MemoryDriver {
    status: DeviceStatus,
}

impl MemoryDriver {
    pub fn new() -> Self {
        MemoryDriver {
            status: DeviceStatus::Uninitialized,
        }
    }
}

impl HalDevice for MemoryDriver {
    fn initialize(&mut self) -> Result<(), HalError> {
        self.status = DeviceStatus::Active;
        Ok(())
    }
    fn shutdown(&mut self) -> Result<(), HalError> {
        self.status = DeviceStatus::Suspended;
        Ok(())
    }
    fn status(&self) -> DeviceStatus {
        self.status
    }
}

/// Stub Network driver.
pub struct NetworkDriver {
    status: DeviceStatus,
}

impl NetworkDriver {
    pub fn new() -> Self {
        NetworkDriver {
            status: DeviceStatus::Uninitialized,
        }
    }
}

impl HalDevice for NetworkDriver {
    fn initialize(&mut self) -> Result<(), HalError> {
        self.status = DeviceStatus::Active;
        Ok(())
    }
    fn shutdown(&mut self) -> Result<(), HalError> {
        self.status = DeviceStatus::Suspended;
        Ok(())
    }
    fn status(&self) -> DeviceStatus {
        self.status
    }
}

// ───────── Tests ─────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_register_and_retrieve_driver() {
        let mut registry = DriverRegistry::new();
        registry.register("cpu", Box::new(CpuDriver::new()));
        registry.register("memory", Box::new(MemoryDriver::new()));

        assert!(registry.get("cpu").is_some());
        assert!(registry.get("memory").is_some());
        assert!(registry.get("gpu").is_none());
        assert_eq!(registry.count(), 2);
    }

    #[test]
    fn test_initialize_all_drivers() {
        let mut registry = DriverRegistry::new();
        registry.register("cpu", Box::new(CpuDriver::new()));
        registry.register("memory", Box::new(MemoryDriver::new()));
        registry.register("network", Box::new(NetworkDriver::new()));

        assert!(registry.initialize_all().is_ok());

        // All drivers should now be Active
        assert_eq!(registry.get("cpu").unwrap().status(), DeviceStatus::Active);
        assert_eq!(
            registry.get("memory").unwrap().status(),
            DeviceStatus::Active
        );
        assert_eq!(
            registry.get("network").unwrap().status(),
            DeviceStatus::Active
        );
    }

    #[test]
    fn test_shutdown_all_drivers() {
        let mut registry = DriverRegistry::new();
        registry.register("cpu", Box::new(CpuDriver::new()));
        registry.register("memory", Box::new(MemoryDriver::new()));
        registry.register("network", Box::new(NetworkDriver::new()));

        registry.initialize_all().unwrap();
        assert!(registry.shutdown_all().is_ok());

        assert_eq!(
            registry.get("cpu").unwrap().status(),
            DeviceStatus::Suspended
        );
        assert_eq!(
            registry.get("memory").unwrap().status(),
            DeviceStatus::Suspended
        );
        assert_eq!(
            registry.get("network").unwrap().status(),
            DeviceStatus::Suspended
        );
    }
}
