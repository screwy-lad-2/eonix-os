//! # Eonix Silicon — Hardware Abstraction Layer
//!
//! Defines compute units, workload hints, compute routing, and the HAL device trait.

use core::fmt;

// ───────── Compute Units ─────────

/// Represents a physical compute unit in the system.
#[derive(Debug, Clone, PartialEq)]
pub enum ComputeUnit {
    CPU { core_id: u8, numa_node: u8 },
    GPU { device_id: u8, vram_mb: u32 },
    NPU { device_id: u8, tops: f32 },
    TPU { device_id: u8, tflops: f32 },
}

impl fmt::Display for ComputeUnit {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ComputeUnit::CPU { core_id, numa_node } => {
                write!(f, "CPU(core={}, numa={})", core_id, numa_node)
            }
            ComputeUnit::GPU { device_id, vram_mb } => {
                write!(f, "GPU(dev={}, vram={}MB)", device_id, vram_mb)
            }
            ComputeUnit::NPU { device_id, tops } => {
                write!(f, "NPU(dev={}, {}TOPS)", device_id, tops)
            }
            ComputeUnit::TPU { device_id, tflops } => {
                write!(f, "TPU(dev={}, {}TFLOPS)", device_id, tflops)
            }
        }
    }
}

// ───────── Workload Hints ─────────

/// Hints the scheduler about what kind of compute a workload needs.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum WorkloadHint {
    GeneralCompute,
    MLInference,
    GraphicsRender,
    MLTraining,
    RealTimeSensor,
}

// ───────── Compute Router ─────────

/// Routes workloads to the best available compute unit.
pub struct ComputeRouter {
    pub available_units: Vec<ComputeUnit>,
}

impl ComputeRouter {
    pub fn new(units: Vec<ComputeUnit>) -> Self {
        ComputeRouter {
            available_units: units,
        }
    }

    /// Route a workload hint to the best matching compute unit.
    ///
    /// Priority logic:
    /// - `MLInference` → NPU first, then GPU, then CPU fallback
    /// - `GraphicsRender` → GPU first, then CPU fallback
    /// - `MLTraining` → TPU first, then GPU, then CPU fallback
    /// - `RealTimeSensor` → first CPU (reserved RTOS core assumption)
    /// - `GeneralCompute` → CPU
    pub fn route(&self, hint: WorkloadHint) -> Option<ComputeUnit> {
        match hint {
            WorkloadHint::MLInference => self
                .find_npu()
                .or_else(|| self.find_gpu())
                .or_else(|| self.find_cpu()),

            WorkloadHint::GraphicsRender => {
                self.find_gpu().or_else(|| self.find_cpu())
            }

            WorkloadHint::MLTraining => self
                .find_tpu()
                .or_else(|| self.find_gpu())
                .or_else(|| self.find_cpu()),

            WorkloadHint::RealTimeSensor => self.find_cpu(),

            WorkloadHint::GeneralCompute => self.find_cpu(),
        }
    }

    fn find_cpu(&self) -> Option<ComputeUnit> {
        self.available_units
            .iter()
            .find(|u| matches!(u, ComputeUnit::CPU { .. }))
            .cloned()
    }

    fn find_gpu(&self) -> Option<ComputeUnit> {
        self.available_units
            .iter()
            .find(|u| matches!(u, ComputeUnit::GPU { .. }))
            .cloned()
    }

    fn find_npu(&self) -> Option<ComputeUnit> {
        self.available_units
            .iter()
            .find(|u| matches!(u, ComputeUnit::NPU { .. }))
            .cloned()
    }

    fn find_tpu(&self) -> Option<ComputeUnit> {
        self.available_units
            .iter()
            .find(|u| matches!(u, ComputeUnit::TPU { .. }))
            .cloned()
    }
}

// ───────── HAL Device Trait ─────────

/// Status of a HAL-managed device.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum DeviceStatus {
    Uninitialized,
    Active,
    Suspended,
    Error,
}

/// Errors that can occur during HAL device operations.
#[derive(Debug, Clone, PartialEq)]
pub enum HalError {
    InitializationFailed(String),
    ShutdownFailed(String),
    DeviceNotFound,
    PermissionDenied,
}

impl fmt::Display for HalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            HalError::InitializationFailed(msg) => write!(f, "Init failed: {}", msg),
            HalError::ShutdownFailed(msg) => write!(f, "Shutdown failed: {}", msg),
            HalError::DeviceNotFound => write!(f, "Device not found"),
            HalError::PermissionDenied => write!(f, "Permission denied"),
        }
    }
}

/// Trait that all HAL-managed hardware devices must implement.
pub trait HalDevice {
    fn initialize(&mut self) -> Result<(), HalError>;
    fn shutdown(&mut self) -> Result<(), HalError>;
    fn status(&self) -> DeviceStatus;
}

// ───────── Tests ─────────

#[cfg(test)]
mod tests {
    use super::*;

    fn make_full_router() -> ComputeRouter {
        ComputeRouter::new(vec![
            ComputeUnit::CPU {
                core_id: 0,
                numa_node: 0,
            },
            ComputeUnit::GPU {
                device_id: 0,
                vram_mb: 8192,
            },
            ComputeUnit::NPU {
                device_id: 0,
                tops: 15.0,
            },
            ComputeUnit::TPU {
                device_id: 0,
                tflops: 45.0,
            },
        ])
    }

    #[test]
    fn test_routes_inference_to_npu() {
        let router = make_full_router();
        let unit = router.route(WorkloadHint::MLInference).unwrap();
        assert!(matches!(unit, ComputeUnit::NPU { .. }));
    }

    #[test]
    fn test_falls_back_to_cpu_when_no_npu() {
        let router = ComputeRouter::new(vec![ComputeUnit::CPU {
            core_id: 0,
            numa_node: 0,
        }]);
        let unit = router.route(WorkloadHint::MLInference).unwrap();
        assert!(matches!(unit, ComputeUnit::CPU { .. }));
    }

    #[test]
    fn test_routes_graphics_to_gpu() {
        let router = make_full_router();
        let unit = router.route(WorkloadHint::GraphicsRender).unwrap();
        assert!(matches!(unit, ComputeUnit::GPU { .. }));
    }
}
