# colt_ui

`colt_ui` contains minimal operator interfaces for Colt development. The first
tool only selects source and target chairs; it does not command navigation,
pan-tilt, arm motion or grasping.

## Terminal Chair Selector

```bash
source devel/setup.bash
rosrun colt_ui terminal_chair_selector.py
```

The selector reads chair candidates from:

```text
/colt/bridle/candidates
```

It publishes latched selections:

```text
/colt/ui/selected_source_chair
/colt/ui/selected_target_chair
```

For non-interactive smoke tests:

```bash
rosrun colt_ui terminal_chair_selector.py --source chair_0 --target chair_1 --no-prompt
```

The process should stay alive so late-starting fusion nodes can receive the
latched selection messages.
