# Endpoint analysis correction

The independent native reviewer found that cycle endpoint selection filtered out unknown logical poses before choosing the final actual display. A correct earlier known pose could therefore be incorrectly reported as the final displayed pose when a later displayed scene had an unknown or conflicting marker.

The analyzer now classifies the **last actual positive presentation**, retaining `known`, `unknown`, `ambiguous`, or `no_actual_display` status. Unknown/ambiguous final pose produces a null endpoint error/tolerance assessment. It cannot pass the all-endpoints correctness check, and unknown versus known-failed cycles are counted separately. Earlier known endpoint arrival and last-known pose remain explicitly labeled supplements; neither replaces the final display.

Seven saved-data synthetic cases passed: known endpoint, known→unknown, known→ambiguous, unknown→known, known→wrong endpoint, no presentation, and two conflicting known poses at one actual timestamp. The latter is deduplicated to one ambiguous display and cannot pass the endpoint check.

This is a documented analysis correctness fix during main acquisition. Acquisition, input, thresholds and metric windows are unchanged. No main raw records were read or reanalyzed for the fix. The prior analyzer, exact diff and test/hash record are preserved in `analyze-before-endpoint-unknown.py`, `endpoint-unknown-correction.patch`, and `endpoint-unknown-correction.json`.
