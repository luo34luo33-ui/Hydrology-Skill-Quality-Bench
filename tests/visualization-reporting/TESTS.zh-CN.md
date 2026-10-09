# 原子任务补齐测试矩阵

新增43题，固定上游输入；只调用确定性技能脚本，不运行Agent。每题结构、文件及科学契约由 task.json 定义。普通拒绝保留原生失败结果和允许的诊断，禁止正常成果；科学QC失败图册只发布失败看板。

| Task | 场景 | 原生状态 | 退出码序列 |
|---|---|---|---|
| `hydroreport-review-001` | study report passes | warning → success | 2,0 |
| `hydroreport-review-002` | timeseries report passes | warning → success | 2,0 |
| `hydroreport-review-003` | spatial report passes | warning → success | 2,0 |
| `hydroreport-review-004` | missing semantic review | warning | 2 |
| `hydroreport-review-005` | numeric tampering | warning | 2 |
| `hydroreport-review-006` | unsupported narrative | warning → warning | 2,2 |
| `hydroreport-review-007` | source hash mismatch | error | 1 |
| `hydroreport-spatial-001` | topology and independent validation | success | 0 |
| `hydroreport-spatial-002` | missing independent validation | success | 0 |
| `hydroreport-spatial-003` | damaged upstream | error | 1 |
| `hydroreport-study-001` | process-supported controlled narrative | success | 0,0 |
| `hydroreport-study-002` | missing process evidence | success | 0,0 |
| `hydroreport-study-003` | incomplete narrative | error | 0,1 |
| `hydroreport-study-004` | overlapping splits | error | 1 |
| `hydroreport-study-005` | immutable evidence modified | error | 0,1 |
| `hydroreport-timeseries-001` | explicit classes and significant peaks | warning | 0 |
| `hydroreport-timeseries-002` | unavailable analysis without parameters | warning | 0 |
| `hydroreport-timeseries-003` | damaged upstream | error | 1 |
| `hydrovisual-calibration-atlas-001` | continuous calibration | success | 0 |
| `hydrovisual-calibration-atlas-002` | event collection | success | 0 |
| `hydrovisual-calibration-atlas-003` | comparison and continuous event slices | success | 0 |
| `hydrovisual-calibration-atlas-004` | missing rainfall | warning | 0 |
| `hydrovisual-calibration-atlas-005` | comparison coverage mismatch | error | 1 |
| `hydrovisual-dem-atlas-001` | full four maps | success | 0 |
| `hydrovisual-dem-atlas-002` | prepare only two maps | warning | 0 |
| `hydrovisual-dem-atlas-003` | upstream warning | warning | 0 |
| `hydrovisual-dem-atlas-004` | upstream hash mismatch | error | 1 |
| `hydrovisual-flood-atlas-001` | confirmed basin rainfall | success | 0 |
| `hydrovisual-flood-atlas-002` | partial rainfall coverage | warning | 0 |
| `hydrovisual-flood-atlas-003` | zero events | warning | 0 |
| `hydrovisual-flood-atlas-004` | upstream hash mismatch | error | 1 |
| `hydrovisual-hydrobase-atlas-001` | three maps | success | 0 |
| `hydrovisual-hydrobase-atlas-002` | upstream warning | warning | 0 |
| `hydrovisual-hydrobase-atlas-003` | scientific FAIL dashboard only | error | 2 |
| `hydrovisual-hydrobase-atlas-004` | upstream hash mismatch | error | 1 |
