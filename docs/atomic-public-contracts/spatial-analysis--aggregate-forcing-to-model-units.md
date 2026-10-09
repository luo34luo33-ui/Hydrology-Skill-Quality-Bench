# Public input/output contract

Identical in all three conditions. Describes interfaces, not expected results.

Preserve double precision (17 significant digits for computed CSV numbers). Resolve manifest artifact paths relative to the manifest directory; bind files by SHA-256. Choose the applicable outcome branch from the evidence; no branch is preselected.

```json
{
  "version": "atomic-three-arm-v2",
  "interface_id": "spatial-analysis/aggregate-forcing-to-model-units",
  "source_contract_sha256": "99ec5d02d0d68fbfe5e8a3799667e068efa00737b32eb26830552c8ab7f08595",
  "interface": {
    "schema_version": "1.0",
    "inputs": [
      {
        "id": "hydrobase",
        "description": "构建 result.json 和单出口独立 QC result.json，哈希一致。",
        "required": true,
        "format": "JSON"
      },
      {
        "id": "source_config",
        "description": "P 与 evap 两层的来源、空间坐标、时间及单位。",
        "required": true,
        "format": "JSON"
      }
    ],
    "outputs": [
      {
        "id": "forcing",
        "description": "流域 time,P,PET 或子流域 time,sub_id,P_mm,E0_mm。",
        "required": true,
        "format": "CSV"
      },
      {
        "id": "weights",
        "description": "逐变量、逐模型单元、逐站点/格点面积权重。",
        "required": true,
        "format": "CSV"
      },
      {
        "id": "coverage",
        "description": "逐变量与模型单元覆盖比例。",
        "required": true,
        "format": "CSV"
      },
      {
        "id": "result",
        "description": "逐输入与产物哈希及 QC。",
        "required": true,
        "format": "JSON"
      }
    ],
    "invariants": [
      "HydroBase QC 必须无 FAIL，且构建哈希吻合。",
      "逐步缺站或缺格点停止，不调整面积权重。"
    ]
  },
  "serialization": {
    "object_structures": [
      {
        "path": {
          "type": "computed; see field semantics"
        },
        "sha256": {
          "type": "computed; see field semantics"
        }
      },
      {
        "schema_version": {
          "type": "string"
        },
        "skill": {
          "type": "computed; see field semantics"
        },
        "status": {
          "type": "string"
        },
        "message": {
          "type": "computed; see field semantics"
        },
        "parameters": {},
        "inputs": {
          "type": "computed; see field semantics"
        },
        "artifacts": {},
        "checks": {
          "type": "array",
          "items": {
            "check": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "details": {
              "type": "computed; see field semantics"
            }
          }
        },
        "warnings": {
          "type": "array",
          "items": {
            "type": "unknown"
          }
        },
        "provenance": {
          "python": {
            "type": "computed; see field semantics"
          }
        }
      },
      {
        "python": {
          "type": "computed; see field semantics"
        }
      },
      {
        "check": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "details": {
          "type": "computed; see field semantics"
        }
      },
      {
        "P": {
          "type": "string"
        },
        "evap": {
          "type": "computed; see field semantics"
        }
      },
      {
        "schema_version": {
          "type": "string"
        },
        "skill": {
          "type": "computed; see field semantics"
        },
        "status": {
          "type": "string"
        },
        "message": {
          "type": "string"
        },
        "parameters": {
          "target": {
            "type": "computed; see field semantics"
          }
        },
        "inputs": {
          "type": "computed; see field semantics"
        },
        "artifacts": {
          "type": "computed; see field semantics"
        },
        "checks": {
          "type": "array",
          "items": {
            "check": {
              "type": "string"
            },
            "status": {
              "type": "string"
            },
            "details": {
              "type": "string"
            }
          }
        },
        "warnings": {
          "type": "array",
          "items": {
            "type": "unknown"
          }
        },
        "provenance": {
          "python": {
            "type": "computed; see field semantics"
          },
          "rasterio": {
            "type": "computed; see field semantics"
          },
          "shapely": {
            "type": "computed; see field semantics"
          }
        }
      },
      {
        "grid": {
          "type": "computed; see field semantics"
        },
        "table": {
          "type": "computed; see field semantics"
        }
      },
      {
        "stations": {
          "type": "computed; see field semantics"
        },
        "result": {
          "type": "computed; see field semantics"
        }
      },
      {
        "basin": {
          "type": "computed; see field semantics"
        }
      },
      {
        "topology_result": {
          "type": "computed; see field semantics"
        },
        "topology_qc_result": {
          "type": "computed; see field semantics"
        },
        "source_config": {
          "type": "computed; see field semantics"
        }
      },
      {
        "target": {
          "type": "computed; see field semantics"
        }
      },
      {
        "python": {
          "type": "computed; see field semantics"
        },
        "rasterio": {
          "type": "computed; see field semantics"
        },
        "shapely": {
          "type": "computed; see field semantics"
        }
      },
      {
        "check": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "details": {
          "type": "string"
        }
      },
      {
        "depth_mm": {
          "type": "string"
        }
      },
      {
        "variable": {
          "type": "computed; see field semantics"
        },
        "unit_id": {
          "type": "computed; see field semantics"
        },
        "coverage_fraction": {
          "type": "computed; see field semantics"
        },
        "covered_area_m2": {
          "type": "computed; see field semantics"
        },
        "unit_area_m2": {
          "type": "computed; see field semantics"
        }
      },
      {
        "unit_id": {
          "type": "string"
        },
        "P": {
          "type": "string"
        },
        "E0": {
          "type": "string"
        }
      },
      {
        "weighted": {
          "type": "computed; see field semantics"
        }
      },
      {
        "value": {
          "type": "computed; see field semantics"
        }
      },
      {
        "forcing": {
          "type": "computed; see field semantics"
        },
        "weights": {
          "type": "string"
        },
        "coverage": {
          "type": "string"
        }
      }
    ],
    "named_field_sets": [
      [
        "success",
        "warning"
      ],
      [
        "path",
        "sha256"
      ],
      [
        "basin_forcing.csv",
        "subbasin_forcing.csv",
        "weights.csv",
        "coverage.csv",
        "result.json"
      ],
      [
        "topology-result",
        "topology-qc-result",
        "source-config",
        "output-dir"
      ],
      [
        "spatial-analysis/build-hydrological-topology"
      ],
      [
        "spatial-analysis/validate-hydrological-topology"
      ],
      [
        "data-processing/prepare-model-forcing-timeseries",
        "data-processing/derive-potential-evapotranspiration"
      ],
      [
        "mm/step",
        "mm/h"
      ],
      [
        "basin",
        "subbasin"
      ],
      [
        "time",
        "unit_id"
      ],
      [
        "unit_id",
        "time",
        "value"
      ],
      [
        "unit_id",
        "time"
      ],
      [
        "time",
        "P",
        "PET"
      ],
      [
        "time",
        "sub_id",
        "P_mm",
        "E0_mm"
      ],
      [
        "source_id",
        "x",
        "y"
      ],
      [
        "time",
        "source_id"
      ],
      [
        "unit_id",
        "source_id",
        "weight",
        "area_m2"
      ],
      [
        "time",
        "path"
      ]
    ],
    "field_names": [
      "E0",
      "E0_mm",
      "P",
      "PET",
      "P_mm",
      "action",
      "allow_nan",
      "always_xy",
      "area_m2",
      "artifacts",
      "as_index",
      "basin",
      "basin_forcing.csv",
      "build_result",
      "check",
      "checks",
      "choices",
      "columns",
      "coverage",
      "coverage.csv",
      "coverage_fraction",
      "covered_area_m2",
      "data-processing/derive-potential-evapotranspiration",
      "data-processing/prepare-model-forcing-timeseries",
      "data_variable",
      "depth_mm",
      "description",
      "details",
      "dimensions",
      "dtype",
      "encoding",
      "ensure_ascii",
      "envelope",
      "evap",
      "exist_ok",
      "file",
      "forcing",
      "grid",
      "grid_crs",
      "how",
      "indent",
      "index",
      "inplace",
      "inputs",
      "kind",
      "layers",
      "manifest",
      "mask",
      "message",
      "min_coverage_fraction",
      "mm/h",
      "mm/step",
      "netcdf",
      "on",
      "output-dir",
      "parameters",
      "parents",
      "path",
      "provenance",
      "python",
      "rasterio",
      "required",
      "result",
      "result.json",
      "schema_version",
      "seconds",
      "sha256",
      "shapely",
      "skill",
      "source-config",
      "source_config",
      "source_id",
      "spatial-analysis/build-hydrological-topology",
      "spatial-analysis/validate-hydrological-topology",
      "station_crs",
      "stations",
      "status",
      "sub_id",
      "subbasin",
      "subbasin_forcing.csv",
      "subbasins_clipped",
      "subbasins_table",
      "success",
      "table",
      "target",
      "time",
      "time_zone",
      "timestamp_semantics",
      "timestep_seconds",
      "topology-qc-result",
      "topology-result",
      "topology_qc_result",
      "topology_result",
      "transform",
      "type",
      "unit",
      "unit_area_m2",
      "unit_id",
      "utc",
      "validate",
      "value",
      "variable",
      "warning",
      "warnings",
      "weight",
      "weighted",
      "weights",
      "weights.csv",
      "x",
      "y"
    ],
    "literal_enum_values": {
      "schema_version": [
        "1.0"
      ],
      "status": [
        "FAIL",
        "PASS",
        "error",
        "success"
      ]
    },
    "static_interface_values": {
      "schema_version": [
        "1.0"
      ]
    },
    "figure_layer_interfaces": [],
    "dynamic_field_patterns": [
      "^grid_.+$",
      "^r.+c.+$",
      "^rows=.+$"
    ],
    "passthrough_policy": "Preserve applicable input columns and configured identifiers. Dynamic output names follow the source interface patterns; tables can carry upstream fields."
  },
  "common_result": {
    "fields": [
      "schema_version",
      "skill",
      "status",
      "message",
      "parameters",
      "inputs",
      "artifacts",
      "checks",
      "warnings",
      "provenance"
    ],
    "status_branches": [
      "success",
      "warning",
      "error"
    ],
    "artifact_reference": {
      "path": "relative to result directory",
      "sha256": "SHA-256 of actual referenced file"
    },
    "skill": "spatial-analysis/aggregate-forcing-to-model-units"
  },
  "precision": "Preserve IEEE-754 double precision; write computed CSV numbers with 17 significant digits; never round intermediate calculations."
}
```
