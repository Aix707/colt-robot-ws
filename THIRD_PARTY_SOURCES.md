# Third Party Sources

This workspace absorbs a few previously nested Git repositories into the top-level
`catkin_ws` repository so the robot workspace can be versioned and deployed as one
unit. Their original source locations and checked revisions are recorded here for
traceability.

| Path | Original remote | Recorded revision |
| --- | --- | --- |
| `src/iai_kinect2` | `https://gitee.com/s-robot/iai_kinect2.git` | `2eb6b71` |
| `src/waterplus_map_tools` | `https://github.com/6-robot/waterplus_map_tools.git` | `a38e5b2` |

Only the nested `.git` metadata directories were removed. Source files remain in
place under the top-level workspace repository.
