//! # Eonix Silicon — Hardware Abstraction Layer
//!
//! Provides unified abstractions over CPU, GPU, NPU, and device sensors.
//! This is the foundation layer (Layer 1) of the Eonix OS architecture.

/// CPU information and capabilities
pub mod cpu {
    /// Detected CPU features relevant to Eonix workloads
    pub struct CpuInfo {
        pub core_count: usize,
        pub thread_count: usize,
        pub has_avx2: bool,
        pub has_npu: bool,
        pub frequency_mhz: u64,
    }

    impl CpuInfo {
        /// Detect CPU capabilities at runtime
        pub fn detect() -> Self {
            CpuInfo {
                core_count: num_cpus(),
                thread_count: num_cpus() * 2, // Assume SMT
                has_avx2: false,               // TODO: cpuid check
                has_npu: false,                // TODO: device detection
                frequency_mhz: 0,             // TODO: read from sysfs
            }
        }
    }

    fn num_cpus() -> usize {
        // Placeholder — in production read from /sys/devices/system/cpu/
        4
    }
}

/// Memory subsystem abstraction
pub mod memory {
    /// System memory information
    pub struct MemoryInfo {
        pub total_bytes: u64,
        pub available_bytes: u64,
        pub huge_pages_supported: bool,
    }
}

/// Device mesh for cross-device hardware sharing
pub mod mesh {
    /// A discovered device on the local network
    pub struct MeshDevice {
        pub device_id: String,
        pub hostname: String,
        pub capabilities: Vec<String>,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cpu_detect() {
        let info = cpu::CpuInfo::detect();
        assert!(info.core_count > 0);
    }
}
