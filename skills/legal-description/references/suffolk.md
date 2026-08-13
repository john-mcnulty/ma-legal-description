# Suffolk County — masslandrecords.com/suffolk/D/Default.aspx

Registry mechanics for the `/legal-description` workflow.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**System:** Avenu/20-20 Perfect Vision Land Records I2 (ASP.NET) — **identical field IDs to Plymouth County**

**Name format:** Same as Plymouth County — last name first in `ACSTextBox_LastName1`, first name in `ACSTextBox_FirstName1`, no special formatting needed.

**Form field IDs:** Same as Plymouth County (see above).

**Image viewer:** Loads **inline** on the page (popup viewer checkbox is unchecked by default). Same `ImageViewer1_docImage` element. `OpenImageViewer()` calls `__doPostBack('ButOpenImageViewer','')`.

**Popup blocker:** The site may show a popup-blocker notification on first use. The user must allow popups for `masslandrecords.com` in Chrome settings before the image viewer will load.

**Image resolution:** Native deed images are served at ~217×281 px (low resolution). Scale up 3× via canvas for usability. Some text (e.g., Master Deed page numbers) may not be clearly legible.

**Renderer freezes:** The renderer frequently becomes unresponsive while loading deed images — screenshot calls will time out. Wait 8–10 seconds and retry. JavaScript calls typically succeed even when screenshots fail; use JS to check page state and capture images.

**Download method:** Same Chrome bulk-download limitation as Plymouth County. Use localStorage + fresh tab for pages 2 and 3.

**Recording cover sheet:** Page 1 is always a Suffolk County recording cover sheet ("Electronically Recorded Document — This is the first page of the document. Do not remove"). The deed content begins on page 2.
