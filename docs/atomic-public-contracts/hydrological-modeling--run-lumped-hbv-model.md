# Public input/output contract

Identical in all three conditions. Describes interfaces, not expected results.

Preserve double precision (17 significant digits for computed CSV numbers). Resolve manifest artifact paths relative to the manifest directory; bind files by SHA-256. Choose the applicable outcome branch from the evidence; no branch is preselected.

```json
{
  "version": "atomic-three-arm-v2",
  "interface_id": "hydrological-modeling/run-lumped-hbv-model",
  "source_contract_sha256": "381e070ea0a9aa91ab00b194413f21335c4818bff253e6009c559076f6869d65",
  "interface": {
    "schema_version": "1.0",
    "inputs": [
      {
        "id": "forcing_table",
        "description": "包含时间、面平均降雨与蒸发能力的 forcing 表；event 模式下可由一个目录或一个多 sheet 工作簿提供多场次。",
        "required": true,
        "format": "CSV, Parquet or XLSX",
        "variables": [
          {
            "name": "P",
            "semantics": "面平均降雨，每步长水深；由调用方确认为面平均值。",
            "units": "mm per time step",
            "time_step": "由 --timestep-hours 显式声明并与时间列推断值一致",
            "state_or_flux": "flux",
            "accumulated_or_instantaneous": "instantaneous",
            "missing_value_semantics": "缺测必须停止；不得静默填 0 或插值后继续。"
          },
          {
            "name": "evap",
            "semantics": "蒸发能力，每步长水深，乘以系数 c 后得到蒸散发需求。",
            "units": "mm per time step",
            "time_step": "由 --timestep-hours 显式声明并与时间列推断值一致",
            "state_or_flux": "flux",
            "accumulated_or_instantaneous": "instantaneous",
            "missing_value_semantics": "缺测必须停止；来源与处理方法由调用方记录。"
          },
          {
            "name": "time",
            "semantics": "严格递增且等间隔的时间索引。",
            "units": "datetime",
            "time_step": "由 --timestep-hours 显式声明并与时间列推断值一致",
            "state_or_flux": "not_applicable",
            "accumulated_or_instantaneous": "not_applicable",
            "missing_value_semantics": "空值或重复值必须停止。"
          }
        ]
      },
      {
        "id": "parameter_set",
        "description": "简化 HBV 9 参数集，全部必填，无静默默认。",
        "required": true,
        "format": "JSON or YAML",
        "variables": [
          {
            "name": "fc",
            "semantics": "土壤持水容量，与 lp 共同决定凋萎点 PWP = lp × fc。",
            "units": "mm",
            "state_or_flux": "state",
            "accumulated_or_instantaneous": "not_applicable",
            "missing_value_semantics": "缺失必须停止，不得使用经验默认值。"
          },
          {
            "name": "c",
            "semantics": "蒸发能力缩放系数，取值落在 0 到 1 之间。",
            "units": "fraction",
            "state_or_flux": "not_applicable",
            "accumulated_or_instantaneous": "not_applicable",
            "missing_value_semantics": "缺失必须停止，不得使用经验默认值。"
          }
        ]
      },
      {
        "id": "basin_properties",
        "description": "流域属性，由 CLI 显式提供：--area-km2（流域面积）、--timestep-hours（时间步长）。",
        "required": true,
        "format": "CLI arguments"
      }
    ],
    "outputs": [
      {
        "id": "simulation_table",
        "description": "逐时步状态与通量表，含出口流量 Q 与产流分量、状态列；event 模式带场次标识列。",
        "required": true,
        "format": "CSV, Parquet or XLSX",
        "variables": [
          {
            "name": "Q",
            "semantics": "流域出口流量，三个线性水库出流之和按面积换算，负值已截断为 0。",
            "units": "m3/s",
            "time_step": "与输入时间步长一致",
            "state_or_flux": "flux",
            "accumulated_or_instantaneous": "instantaneous",
            "missing_value_semantics": "QC 失败时不产出；不写 NaN。"
          },
          {
            "name": "SM",
            "semantics": "土壤含水量状态，非负。",
            "units": "mm",
            "time_step": "与输入时间步长一致",
            "state_or_flux": "state",
            "accumulated_or_instantaneous": "instantaneous",
            "missing_value_semantics": "QC 失败时不产出；不写 NaN。"
          },
          {
            "name": "RECHARGE",
            "semantics": "进入响应层的补给量，由有效雨乘以蓄满修正项得到，含源码固有的消减损耗。",
            "units": "mm per time step",
            "time_step": "与输入时间步长一致",
            "state_or_flux": "flux",
            "accumulated_or_instantaneous": "instantaneous",
            "missing_value_semantics": "QC 失败时不产出；不写 NaN。"
          }
        ]
      },
      {
        "id": "event_index",
        "description": "event 模式下的场次清单，记录每场的行数、起止时间与预热步数。",
        "required": false,
        "format": "CSV"
      },
      {
        "id": "run_result",
        "description": "符合 HydroTune 运行结果约定的 result.json，含参数、输入与产物 SHA-256、QC 与 provenance。",
        "required": true,
        "format": "JSON"
      }
    ],
    "warmup_period": {
      "required": false,
      "semantics": "由 --warmup-steps 显式声明的前 N 步标记 is_warmup 且不纳入模拟期统计；源码没有 warmup 机制，标记段照常从零状态递推。"
    },
    "simulation_period": {
      "required": true,
      "semantics": "扣除预热后的全部时步；模拟期为空即失败，退出码 2。"
    },
    "invariants": [
      "时间轴必须严格递增、等间隔，并与 --timestep-hours 一致。",
      "蓄水状态 SM、SUZ、SLZ 必须非负（源码 floor 0 兜底）。",
      "状态与通量必须全部有限，出现 NaN 或 Inf 即失败。",
      "水量平衡残差以 warning 报告：源码的 Q0 不从 SM 扣水、effective 到 recharge 有消减项，属结构性损耗而非实现错误。",
      "输出只写入 --output-dir，forcing 缺测或参数越界即停止，不静默填充也不静默复用旧结果。",
      "本 Skill 无雪模块，不含积雪与融雪过程。"
    ]
  },
  "serialization": {
    "object_structures": [
      {
        "fc": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "beta": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "c": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "k0": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "l": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "k1": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "k2": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "kp": {
          "type": "array",
          "items": {
            "type": "number"
          }
        },
        "lp": {
          "type": "array",
          "items": {
            "type": "number"
          }
        }
      },
      {
        "P": {
          "type": "computed; see field semantics"
        },
        "PET": {
          "type": "computed; see field semantics"
        },
        "EA": {
          "type": "computed; see field semantics"
        },
        "SM": {
          "type": "computed; see field semantics"
        },
        "RECHARGE": {
          "type": "computed; see field semantics"
        },
        "SUZ": {
          "type": "computed; see field semantics"
        },
        "SLZ": {
          "type": "computed; see field semantics"
        },
        "Q0": {
          "type": "computed; see field semantics"
        },
        "Q1": {
          "type": "computed; see field semantics"
        },
        "Q2": {
          "type": "computed; see field semantics"
        },
        "Q": {
          "type": "computed; see field semantics"
        },
        "clip_count": {
          "type": "computed; see field semantics"
        }
      },
      {
        "path": {
          "type": "computed; see field semantics"
        },
        "sha256": {
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
        "pandas": {
          "type": "computed; see field semantics"
        }
      },
      {
        "name": {
          "type": "computed; see field semantics"
        },
        "status": {
          "type": "computed; see field semantics"
        },
        "message": {
          "type": "computed; see field semantics"
        }
      },
      {
        "rows": {
          "type": "computed; see field semantics"
        },
        "warmup_steps": {
          "type": "computed; see field semantics"
        },
        "simulation_steps": {
          "type": "computed; see field semantics"
        },
        "precipitation_total_mm": {
          "type": "computed; see field semantics"
        },
        "runoff_total_mm": {
          "type": "computed; see field semantics"
        },
        "peak_q_m3_s": {
          "type": "computed; see field semantics"
        },
        "clip_count": {
          "type": "computed; see field semantics"
        }
      },
      {
        "simulation_table": {
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
          "type": "computed; see field semantics"
        },
        "message": {
          "type": "computed; see field semantics"
        },
        "parameters": {
          "mode": {
            "type": "computed; see field semantics"
          },
          "area_km2": {
            "type": "computed; see field semantics"
          },
          "timestep_hours": {
            "type": "computed; see field semantics"
          },
          "warmup_steps": {
            "type": "computed; see field semantics"
          },
          "balance_tolerance_fraction": {
            "type": "computed; see field semantics"
          },
          "carry_columns": {
            "type": "computed; see field semantics"
          },
          "parameter_set": {
            "type": "computed; see field semantics"
          }
        },
        "inputs": {
          "params": {
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
          "type": "computed; see field semantics"
        },
        "provenance": {
          "type": "computed; see field semantics"
        }
      },
      {
        "time": {
          "type": "computed; see field semantics"
        },
        "is_warmup": {
          "type": "computed; see field semantics"
        }
      },
      {
        "mode": {
          "type": "computed; see field semantics"
        },
        "area_km2": {
          "type": "computed; see field semantics"
        },
        "timestep_hours": {
          "type": "computed; see field semantics"
        },
        "warmup_steps": {
          "type": "computed; see field semantics"
        },
        "balance_tolerance_fraction": {
          "type": "computed; see field semantics"
        },
        "carry_columns": {
          "type": "computed; see field semantics"
        },
        "parameter_set": {
          "type": "computed; see field semantics"
        }
      },
      {
        "params": {
          "type": "computed; see field semantics"
        }
      },
      {
        "checks": {
          "type": "computed; see field semantics"
        },
        "warnings": {
          "type": "computed; see field semantics"
        }
      },
      {
        "rows": {
          "type": "computed; see field semantics"
        },
        "start": {
          "type": "computed; see field semantics"
        },
        "end": {
          "type": "computed; see field semantics"
        },
        "warmup_steps": {
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
        "parameters": {},
        "inputs": {},
        "artifacts": {},
        "provenance": {
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
        "inputs": {},
        "artifacts": {},
        "checks": {
          "type": "array",
          "items": {
            "type": "unknown"
          }
        },
        "warnings": {
          "type": "array",
          "items": {
            "type": "unknown"
          }
        },
        "provenance": {
          "type": "computed; see field semantics"
        }
      }
    ],
    "named_field_sets": [
      [
        "fc",
        "beta",
        "c",
        "k0",
        "l",
        "k1",
        "k2",
        "kp",
        "lp"
      ],
      [
        "csv",
        "parquet",
        "xlsx"
      ],
      [
        ".csv",
        ".parquet",
        ".xlsx"
      ],
      [
        "lumped_hbv_runoff.csv",
        "lumped_hbv_runoff.parquet",
        "lumped_hbv_runoff.xlsx",
        "event_index.csv",
        "result.json"
      ],
      [
        "P",
        "PET",
        "EA",
        "SM",
        "RECHARGE",
        "SUZ",
        "SLZ",
        "Q0",
        "Q1",
        "Q2",
        "Q"
      ],
      [
        "SM",
        "SUZ",
        "SLZ",
        "Q0",
        "Q1",
        "Q2",
        "Q"
      ],
      [
        "event",
        "continuous"
      ]
    ],
    "field_names": [
      ".csv",
      ".parquet",
      ".xlsx",
      "E0",
      "EA",
      "P",
      "PET",
      "Q",
      "Q0",
      "Q1",
      "Q2",
      "RECHARGE",
      "SLZ",
      "SM",
      "SUZ",
      "action",
      "area_km2",
      "artifacts",
      "balance_tolerance_fraction",
      "beta",
      "c",
      "carry_columns",
      "checks",
      "choices",
      "clip_count",
      "continuous",
      "csv",
      "date_format",
      "default",
      "description",
      "dtype",
      "encoding",
      "end",
      "engine",
      "ensure_ascii",
      "errors",
      "event",
      "event_id",
      "event_index",
      "event_index.csv",
      "exist_ok",
      "fc",
      "file",
      "frozen",
      "help",
      "ignore_index",
      "indent",
      "index",
      "inputs",
      "is_warmup",
      "k0",
      "k1",
      "k2",
      "kp",
      "l",
      "lp",
      "lumped_hbv_runoff.csv",
      "lumped_hbv_runoff.parquet",
      "lumped_hbv_runoff.xlsx",
      "message",
      "mode",
      "name",
      "numpy",
      "pandas",
      "parameter_set",
      "parameters",
      "params",
      "parents",
      "parquet",
      "path",
      "peak_q_m3_s",
      "precipitation_total_mm",
      "provenance",
      "python",
      "required",
      "result.json",
      "rows",
      "runoff_total_mm",
      "schema_version",
      "sha256",
      "sheet_name",
      "simulation_steps",
      "simulation_table",
      "skill",
      "sort_keys",
      "start",
      "status",
      "time",
      "timestep_hours",
      "type",
      "warmup_steps",
      "warnings",
      "xlsx"
    ],
    "literal_enum_values": {
      "schema_version": [
        "1.0"
      ],
      "status": [
        "error"
      ]
    },
    "static_interface_values": {
      "schema_version": [
        "1.0"
      ]
    },
    "figure_layer_interfaces": [],
    "dynamic_field_patterns": [
      "^.+:evaporation_coefficient$",
      "^.+:finite_states$",
      "^.+:no_missing_forcing$",
      "^.+:numerical_clipping$",
      "^.+:parameter_range$",
      "^.+:state_bounds$",
      "^.+:time_axis_regular$",
      "^.+:warmup_coverage$",
      "^.+:water_balance$",
      "^\\.6g$",
      "^lumped_hbv_runoff\\..+$"
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
    "skill": "hydrological-modeling/run-lumped-hbv-model"
  },
  "precision": "Preserve IEEE-754 double precision; write computed CSV numbers with 17 significant digits; never round intermediate calculations."
}
```
