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
- **draw.io output:** no. Set to yes to have the diagrammer also save a `.drawio` file, built with
  `kit-drawio` from a JSON copy of its spec, next to the editable file the standard names.
- **Recipe:** optional. The steps that produce a finished diagram, including any tool that fills in
  title blocks or legends. Kit's `vsdx-finish` does that for Visio files; set it up in
  `vsdx-finish.json`, next to this file.
- **Stencils:** optional. The shape libraries the standard calls for, and where they are.
- **Lint rules:** optional. The path of a JSON rules file that `kit-diaglint` checks diagrams
  against: palette, fonts, title block fields, legend, line types, connectors, shapes, page names,
  and view labels. Start from Kit's `diagram-lint-rules.example.json` in the templates folder and
  keep your copy next to this file, since it holds your standard's details.
