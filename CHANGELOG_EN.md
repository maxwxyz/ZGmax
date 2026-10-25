# ZGmax – Change history

## Version 2.1 of 2026-10-25

- Comparison: paper flattening for scans, exact character check for similar digits (e.g. 41.8 → 43.2), suggestion of the exact vector comparison for PDFs, turn rejected hits into zones.
- Manual alignment with two or three points.
- Text recognition German/English (umlauts, ß, °, ±); text search in PDF text or via text recognition, hits also in the new drawing.
- Read comments from XFDF and PDF annotations and save them as XFDF; replies and review status per person (as in Acrobat and Bluebeam).
- English user interface (system language) and English manuals; adjustable interface size.
- Measuring: dimensions drawn like dimensioning, dimension chains, sums and counts, measurements as CSV, scale and calibration per page, CAD snap to centers, corners, intersections and end points, origin and coordinate input.
- Drawing tools: pen, ellipse, line, polyline, polygon, text directly in the drawing; tool chest with presets and custom stamps.
- Layers, drawing editing (move an area), searchable PDF, vectorize (SVG, PDF, DXF), redaction.
- Crop as an adjustable frame for outputs; show and hide single markups.
- Multi-page files: markups and review state per page, page list with counts, page selector at the top and Page Up/Down, PDF with annotations and change report across all pages.
- Clean up scans: background, straighten, rectify a photo of a sheet.
- Line filter: contours only, thin lines only or a custom stroke width – when viewing and comparing; for vector PDFs using the real stroke widths.
- Change list: “Contours and dimensions” filter, undo also for delete, status and comments, renumber, Backspace deletes; report, CSV and image contain only the entries of the list.
- Handling: double-click a tool = keep tool; Shift = move horizontally/vertically, line in 45° steps, circle, square; snapping to other markups; copy the view as shown to the clipboard; back to the drawing from the start page.
- Project as a container: the drawings are embedded in the .zgmax file and can be sent along with it; program version stored in the project.
- Save views (View → Saved views, Ctrl+D) and jump back with one click; print to scale also for the visible area or a selected area, with footer.
- Manuals: new section “All menu commands”, generated automatically from the menus; the menu item “View drawing” is now called “Open single drawing”.
- “Start review”: one button finds the changes, shows the first open one and shows the keys; introduction in three steps at the first start.
- Complete review: reviewer, result (approved, with conditions, not approved) and remark as a review record with checksum in the project and as PDF.
- Dimension changes as table (PDF/CSV) with dimension old → new, tolerance old/new (ISO fit, ±, deviations), position and review status.
- Compare folders: own release against a supplier data set, all pages, subfolders, revision letter in the name can be ignored; overview (changed, identical, only old/new) as table, PDF and CSV.
- Search fields above the change list and the markup list.
- Versions with change history (Help → What's new).
- License AGPL-3.0.
- Fixed: menu icons in light mode, overlapping check boxes in lists, a selected change could not be deselected, “Comparing …” shown when only viewing, a started markup stuck to the mouse pointer after a cancelled dialog, “Fit to paper” when printing with the English interface; the area selection button “Delete” is now called “Remove markups”.

## Version 2.0 of 2026-10-22

- Baseline: viewer and comparison with alignment, tile fine alignment, moved blocks and objects, change list with review status, markups, measuring, project, PDF report, batch and revisions, command line.
