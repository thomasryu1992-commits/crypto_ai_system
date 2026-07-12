# Step243 v5 Canonical Port Plan for Root-Only Legacy Features

## Purpose

Step243 groups root-only legacy imports into canonical port groups.

It is a plan-only step. It does not port code, rewrite imports, or convert root packages into wrappers.

## Added

- `scripts/plan_canonical_ports_for_root_only_features.py`
- `tests/test_step243_canonical_port_plan.py`
- JSON / CSV / Markdown canonical port plan outputs

## Why This Exists

Step242 showed that the remaining legacy root imports require root-only feature porting before wrapper conversion.

## Next Step

Step244 should implement a small first canonical port batch with tests.

## Safety

Step243 does not enable:

- paper execution
- adapter routing
- external API calls
- Telegram real sends
- live trading
