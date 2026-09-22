"""Exceptions raised by the tool layer.

`ToolInputError` is for genuinely bad calls -- an unknown plant name, a
malformed period, an out-of-range parameter. It is the caller's (the
agent's, or a test's) mistake, so it is raised immediately rather than
folded into the structured result.

Data-level problems that exist in the dataset itself (missing rows,
conflicting rows, an implausible value) are never exceptions: they are
reported in the tool's returned `status`/`issues` fields, because the agent
needs to see and report them, not have the call blow up. See
`app/tools/_common.py`.
"""


class ToolInputError(ValueError):
    pass
