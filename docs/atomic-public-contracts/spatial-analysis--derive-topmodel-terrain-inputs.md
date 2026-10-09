# Public input/output contract

Identical in all three conditions. Describes interfaces, not expected results.

Preserve double precision (17 significant digits for computed CSV numbers). Resolve manifest artifact paths relative to the manifest directory; bind files by SHA-256. Choose the applicable outcome branch from the evidence; no branch is preselected.

```json
{
  "version": "atomic-three-arm-v2",
  "interface_id": "spatial-analysis/derive-topmodel-terrain-inputs",
  "source_contract_sha256": "6ee2ca298270aa45807c29b9677195a8142517159be472d18164a56f06a22361",
  "interface": {
    "schema_version": "1.0",
    "inputs": [
      {
        "id": "stream_result",
        "required": true,
        "format": "JSON",
        "description": "Hashed stream extraction result with filled DEM D8 and accumulation raster."
      },
      {
        "id": "topology_result",
        "required": true,
        "format": "JSON",
        "description": "Hashed HydroBase result with true basin raster."
      },
      {
        "id": "topology_qc_result",
        "required": true,
        "format": "JSON",
        "description": "Matching independent single outlet topology QC with no FAIL."
      },
      {
        "id": "classes",
        "required": true,
        "format": "integer",
        "description": "Explicit topographic index class count at least two."
      },
      {
        "id": "distance_bins",
        "required": true,
        "format": "integer",
        "description": "Explicit distance area bin count at least one."
      },
      {
        "id": "minimum_slope",
        "required": true,
        "format": "number",
        "description": "Explicit positive dimensionless D8 slope floor."
      }
    ],
    "outputs": [
      {
        "id": "topographic_index",
        "required": true,
        "format": "GeoTIFF",
        "description": "Natural log of specific catchment area over D8 slope."
      },
      {
        "id": "topographic_index_classes",
        "required": true,
        "format": "CSV",
        "description": "Mean topographic index and basin area fraction per class."
      },
      {
        "id": "distance_area",
        "required": true,
        "format": "CSV",
        "description": "D8 outlet distance and cumulative basin area."
      },
      {
        "id": "run_result",
        "required": true,
        "format": "JSON",
        "description": "Input and output hashes clipped slope count and QC."
      }
    ],
    "invariants": [
      "Each true-basin cell follows D8 to the sole outlet.",
      "Area fractions sum to one; final cumulative area equals basin area.",
      "All input artifacts and upstream result hashes match before calculation."
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
          "type": "string"
        },
        "parameters": {
          "classes": {
            "type": "computed; see field semantics"
          },
          "distance_bins": {
            "type": "computed; see field semantics"
          },
          "minimum_slope": {
            "type": "computed; see field semantics"
          },
          "slope_method": {
            "type": "string"
          },
          "specific_area": {
            "type": "string"
          },
          "d8_encoding": {
            "type": "string"
          },
          "basin_area_m2": {
            "type": "computed; see field semantics"
          },
          "cell_area_m2": {
            "type": "computed; see field semantics"
          },
          "exit_cell": {
            "type": "computed; see field semantics"
          },
          "slope_clipped_cells": {
            "type": "computed; see field semantics"
          }
        },
        "inputs": {
          "stream_result": {
            "type": "computed; see field semantics"
          },
          "topology_result": {
            "type": "computed; see field semantics"
          },
          "topology_qc_result": {
            "type": "computed; see field semantics"
          },
          "subbasins_clipped": {
            "type": "computed; see field semantics"
          }
        },
        "artifacts": {
          "type": "computed; see field semantics"
        },
        "checks": {
          "type": "computed; see field semantics"
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
          "numpy": {
            "type": "computed; see field semantics"
          },
          "rasterio": {
            "type": "computed; see field semantics"
          }
        }
      },
      {
        "classes": {
          "type": "computed; see field semantics"
        },
        "distance_bins": {
          "type": "computed; see field semantics"
        },
        "minimum_slope": {
          "type": "computed; see field semantics"
        },
        "slope_method": {
          "type": "string"
        },
        "specific_area": {
          "type": "string"
        },
        "d8_encoding": {
          "type": "string"
        },
        "basin_area_m2": {
          "type": "computed; see field semantics"
        },
        "cell_area_m2": {
          "type": "computed; see field semantics"
        },
        "exit_cell": {
          "type": "computed; see field semantics"
        },
        "slope_clipped_cells": {
          "type": "computed; see field semantics"
        }
      },
      {
        "stream_result": {
          "type": "computed; see field semantics"
        },
        "topology_result": {
          "type": "computed; see field semantics"
        },
        "topology_qc_result": {
          "type": "computed; see field semantics"
        },
        "subbasins_clipped": {
          "type": "computed; see field semantics"
        }
      },
      {
        "python": {
          "type": "computed; see field semantics"
        },
        "numpy": {
          "type": "computed; see field semantics"
        },
        "rasterio": {
          "type": "computed; see field semantics"
        }
      },
      {
        "check": {
          "type": "computed; see field semantics"
        },
        "status": {
          "type": "string"
        },
        "details": {
          "type": "string"
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
        "parameters": {
          "classes": {
            "type": "computed; see field semantics"
          },
          "distance_bins": {
            "type": "computed; see field semantics"
          },
          "minimum_slope": {
            "type": "computed; see field semantics"
          }
        },
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
        "classes": {
          "type": "computed; see field semantics"
        },
        "distance_bins": {
          "type": "computed; see field semantics"
        },
        "minimum_slope": {
          "type": "computed; see field semantics"
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
      }
    ],
    "named_field_sets": [
      [
        "topographic_index.tif",
        "topographic_index_classes.csv",
        "distance_area.csv",
        "result.json"
      ],
      [
        "stream-result",
        "topology-result",
        "topology-qc-result",
        "output-dir"
      ],
      [
        "success",
        "warning"
      ],
      [
        "filled_dem",
        "d8_pointer",
        "flow_accumulation"
      ],
      [
        "metre",
        "meter",
        "metres",
        "meters"
      ],
      [
        "class_id",
        "ti_lower",
        "ti_upper",
        "ti_mean",
        "cell_count",
        "area_fraction"
      ],
      [
        "bin_id",
        "distance_m",
        "cumulative_cells",
        "cumulative_area_m2",
        "cumulative_fraction"
      ],
      [
        "path",
        "sha256"
      ],
      [
        "upstream_hashes",
        "single_outlet",
        "same_grid",
        "d8_paths",
        "finite_index",
        "distribution_weights"
      ]
    ],
    "field_names": [
      "action",
      "allow_nan",
      "area_fraction",
      "artifacts",
      "basin_area_m2",
      "bin_id",
      "cell_area_m2",
      "cell_count",
      "check",
      "checks",
      "class_id",
      "classes",
      "count",
      "cumulative_area_m2",
      "cumulative_cells",
      "cumulative_fraction",
      "d8_encoding",
      "d8_paths",
      "d8_pointer",
      "description",
      "details",
      "distance_area.csv",
      "distance_bins",
      "distance_m",
      "distribution_weights",
      "dtype",
      "encoding",
      "ensure_ascii",
      "exist_ok",
      "exit_cell",
      "file",
      "filled_dem",
      "finite_index",
      "flow_accumulation",
      "indent",
      "inputs",
      "message",
      "meter",
      "meters",
      "metre",
      "metres",
      "minimum_slope",
      "newline",
      "nodata",
      "numpy",
      "output-dir",
      "parameters",
      "parents",
      "path",
      "provenance",
      "python",
      "rasterio",
      "required",
      "result.json",
      "same_grid",
      "schema_version",
      "sha256",
      "single_outlet",
      "skill",
      "slope_clipped_cells",
      "slope_method",
      "specific_area",
      "status",
      "stream-result",
      "stream_result",
      "subbasins_clipped",
      "success",
      "ti_lower",
      "ti_mean",
      "ti_upper",
      "topographic_index.tif",
      "topographic_index_classes.csv",
      "topology-qc-result",
      "topology-result",
      "topology_qc_result",
      "topology_result",
      "type",
      "upstream_hashes",
      "warning",
      "warnings"
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
    "dynamic_field_patterns": [],
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
    "skill": "spatial-analysis/derive-topmodel-terrain-inputs"
  },
  "precision": "Preserve IEEE-754 double precision; write computed CSV numbers with 17 significant digits; never round intermediate calculations."
}
```
