# 04 — Sound

Sound cues in the browser. Runs as is (no model, nothing written).

- The inline **PD Sound** passes PD Load's images through unchanged and plays **ding** when the flow reaches it (`play_when` **node reached**). Put one after each stage of a long graph to hear progress.
- The **PD Sound** on its own plays **chime** when the whole queue has finished. A node with nothing connected always waits for the queue.
- If a run fails, the inline node plays the error buzzer instead (`error_tone`). To hear it, type a file name that doesn't exist into PD Load and run.

**test sound** plays a node's sound. Sounds play in the browser tab that queued the run; `when_cached` also plays when the node is skipped because nothing changed.

**Nodes:** PD Load, PD Sound (×2), Preview Image
