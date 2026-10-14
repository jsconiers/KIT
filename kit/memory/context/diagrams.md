# Diagram setup

What the diagrammer uses. It reads this before every job, so keep it current. If your diagramming
standard is internal, keep its details here: your copy of this file stays on your computer, and the repo
only has this blank template.

- **Standard:** not set. Where to read it, the source file formats it accepts, how to name files,
  and what every diagram must carry, such as a title block and a legend.
- **Colors and lines:** not set. The palette and what each color means, and each line type with its
  color, pattern, and weight.
- **Tools:** not set. The drawing tools and generators on this computer, with the exact commands that
  work: for example the draw.io command line for images, or a Mermaid-to-Visio converter such as
  mmd2vsdx. Give each run a time limit, because a stuck export would hang the job.
- **Recipe:** optional. The steps that produce a finished diagram, including any tool that fills in
  title blocks or legends. Kit's `vsdx-finish` does that for Visio files; set it up in
  `vsdx-finish.json`, next to this file.
- **Stencils:** optional. The shape libraries the standard calls for, and where they are.
