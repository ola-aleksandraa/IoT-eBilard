Three unmodified 1920×1080 PNG frames were supplied by the user on 2026-10-30
for backend testing. The original room photos stay local and are not committed.
Put them in `backend/evaluation-output/photos/` as `table-1.png`, `table-2.png`
and `table-3.png`, or point `EBILARD_PHOTO_DIR` at another directory. Photo tests
skip explicitly when these optional inputs are absent. Synthetic multi-table
tests run without external inputs. The application never imports test data.

`annotations.json` contains approximate, manually inspected ball centers in
source pixels. It includes 11, 3 and 17 visible ball bodies respectively. The
partially visible red object in the upper-right pocket of the second frame is
excluded from the on-cloth layout. Categories on pale, blurred or occluded
bodies are ambiguous; only the cue reference is used for category regression.

The tests enforce a one-to-one match within 25 pixels and current minimum
recall, not perfect localization or classification. The first frame still loses
four balls beside the rails/hand; the third still loses one rail-adjacent ball.
The second frame's former chain of five false cushion balls must stay absent.
These are three views of one physical table, not a multi-table accuracy study.
