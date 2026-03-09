//! # Eonix Silicon — Hardware Abstraction Layer
//!
//! Provides unified abstractions over CPU, GPU, NPU, and device sensors.
//! This is the foundation layer (Layer 1) of the Eonix OS architecture.

pub mod hal;
pub mod drivers;
pub mod mesh;

// Re-export key types at crate root for convenience
pub use hal::{ComputeUnit, ComputeRouter, WorkloadHint, DeviceStatus, HalDevice, HalError};
pub use drivers::{DriverRegistry, CpuDriver, MemoryDriver, NetworkDriver};
pub use mesh::device_discovery::{DeviceMesh, EonixDevice, DeviceType};
