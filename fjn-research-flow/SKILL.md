---
name: fjn-research-flow
description: 'Use when: planning or executing feed-forward 3D/4D Gaussian Splatting or feed-forward point/depth/geometry research, including universal 3D/world reconstruction models with direct 3DGS/Gaussian heads, paper/repo scouting, target-contract candidate usability screening, anti-omission variant checks, 扩展收集论文规则, omission-driven rule expansion, metadata JSON mirrors, popularity scoring, uniqueness notes, maturity grading, P0/P1/P2 and G0/G1/G2/G3 screening.'
argument-hint: 'research scope or step, e.g. step1 quick scouting'
user-invocable: true
---

# Research Flow

## When To Use

Use this skill for research workflows about feed-forward 3D/4D Gaussian Splatting, feed-forward point/depth/geometry methods, driving/urban GS, geometry-prior GS, surface/mesh GS, and autonomous-driving simulation synthetic data.

Use it when the user asks to:

1. Plan a GS literature/repository survey.
2. Execute quick scouting for papers and repositories.
3. Build candidate paper/repo lists with recent-result coverage.
4. Grade methods by P0/P1/P2 and G0/G1/G2/G3.
5. Convert a broad research question into staged deliverables.
6. Expand paper/repository collection rules after the user identifies a missed method or repository.

## Core Principles

1. Keep macro plans concise; move operational detail into separate step files.
2. Separate priority from readiness:
   1. P0/P1/P2 = topic importance.
   2. G0/G1/G2/G3 = execution maturity and Go/No-Go readiness.
3. Always protect against recent-result omission:
   1. Main window: last two years.
   2. Recent watch window: last 1-2 months.
   3. Mature framework window: last one year with code/weights/demo.
   4. Before candidate admission, run a frontier omission audit over the current year and previous year. This audit must include official proceedings / project / README surfaces, not only aggregator APIs or star-sorted GitHub search.
   5. If the candidate pool is dominated by old high-star repositories, treat that as a premature-convergence warning, not as evidence that the direction is saturated. Run current-year top-venue, recent arXiv/month-window, and GitHub `created:>=YYYY-01-01` sweeps before writing conclusions.
   6. If no current frontier hit is found, write a staleness diagnosis that says which official sources were checked, which query axes were negative, and whether the absence is a genuine route signal or an access/search limitation.
   7. For P0/P1 candidates, venue and date fields must be checked against official source surfaces when possible: proceedings/OpenAccess page, OpenReview/forum page, project page, repository README/BibTeX, or publisher page. Aggregators may seed candidates but do not override official sources.
   8. Record the active `metadata.md` display filter before finalizing the catalog. The full candidate universe belongs in `metadata.json`; Markdown is a screened view unless the user explicitly asks for full display.
4. Avoid redundant notes. Record only the minimal facts needed for routing into the next stage.
5. Apply a paper quality gate before finalizing candidate lists:
   1. Keep confirmed top-tier conference or top-journal papers.
   2. Keep unpublished arXiv papers only when there is clear big-tech, major-lab, or established flagship-lab evidence and the topic is directly relevant.
   3. Exclude arXiv-only papers from unknown or weakly established groups when there is no top-venue signal, no strong project signal, and no mature repository.
   4. Exclude repo-only announcements from paper watchlists unless they correspond to retained papers or mature frameworks.
6. Separate methods from platforms:
   1. Method candidates are papers or repositories that directly propose a feed-forward 3D/4D GS technique.
   2. Platform candidates are engineering bases that provide datasets, scene graphs, preprocessing, simulation, rendering, or asset pipelines.
   3. Platform entries must be cataloged separately in metadata and never promoted into the main method pool unless they also satisfy the method criteria.
   4. Platform/tool classification is not publication status. Never infer `no paper`, `repo-only`, or `无论文摘要` only because an entry is a platform, viewer, workflow, renderer, or engineering base.
   5. For every platform/tool entry, check README, project page, Paper/arXiv/DOI/BibTeX links, and cited published-work dependencies before writing publication status. Classify the association as own paper, project paper, related published work, publication artifact/pending, or checked no-formal-paper.
   6. If no paper is found, record the checked-negative source surface explicitly. Use conservative wording such as `未确认正式论文；README/project page checked` rather than blanket `平台项无论文摘要`.
   7. Universal 3D reconstruction, geometric prediction, or world-model papers count as feed-forward GS method candidates when they directly predict 3D Gaussians / 3DGS parameters / `splats` in a single forward pass, even if the title and primary framing do not contain `Gaussian Splatting` or `3DGS`.
   8. If such a universal model also predicts point maps, depth, normals, cameras, mesh, or semantic outputs, catalog it in the GS route when the direct Gaussian head is public and separately cross-reference the geometry/world-model route as needed.
7. Track 4D terminology explicitly:
   1. Distinguish broad dynamic 4D-related ecosystems from true 4DGS method papers.
   2. Record whether a claimed 4D result is feed-forward, optimization-based, editing-oriented, compression-oriented, or simulation-oriented.
   3. State clearly when the current pool does or does not contain a mature feed-forward 4DGS main line.
8. Keep metadata isolated from analysis:
   1. `metadata.md` is a catalog only. It should contain related papers, repositories, projects, methods, integration platforms, and their metadata.
   2. Keep lineage explanations, scope decisions, taxonomy notes, application analysis, limitations, and route recommendations in separately named Markdown files based on their content.
   3. Survey papers, review papers, reading lists, and summary blogs are research references, not candidate methods or platforms. Record them in a separately named reference file such as `survey_and_blog_notes.md`; do not write them into `metadata.md` or `metadata.json` unless the user explicitly asks for a bibliography catalog.
   4. Maintain a JSON mirror of the catalog as `metadata.json` whenever `metadata.md` is created or materially updated.
   5. Treat `metadata.json` as the canonical full catalog. The Markdown version may be a filtered human-readable display of that catalog when the current task benefits from screening rows; if so, state the display filter explicitly and keep every Markdown row traceable to one JSON `catalog` entry. By default, apply different gates for code-backed and no-code entries. Code-backed entries may be displayed when they satisfy at least one gate: arXiv/preprint date within 18 months of the scoring/current research date, formal acceptance/publication date within 12 months, or visible popularity at least half of the catalog maximum (`stars >= 0.5 * max_stars`). No-code, code-not-yet-released, and closed-source entries may be displayed only when they have formal conference/journal acceptance or publication within 6 months. Keep entries that satisfy none of these gates only in `metadata.json`, unless the user asks for a full watchlist or historical view.
   6. Every metadata consolidation must retrieve a compact abstract-grounded innovation point for each catalog entry. Store it in `metadata.json.catalog[].abstract_innovation`, with `abstract_innovation_source` and `abstract_innovation_status`. Prefer the paper abstract from an official paper page, arXiv, OpenAlex, Semantic Scholar, publisher page, or official PDF. If the full abstract is unavailable, use the closest official project page or README and mark the entry as abstract-pending; do not infer detailed mechanisms from title-only evidence.
   7. For platform/tool entries, store repo-to-paper linkage in `metadata.json.catalog[].paper_association`, `paper_association_source`, and `paper_association_status`. This is required even when the row remains in a separate platform section.
   8. In `metadata.md`, replace the old status/remarks table column with `摘要创新点`, and keep operational maturity / source caveats in JSON fields or separate notes. Do not show `生成模式` by default in the human table; keep `generation_mode` in `metadata.json` for route analysis and technical evolution notes.
   9. If `metadata.md` intentionally displays the full catalog, mark the display mode as `full`, write the user/task reason, and keep the compact filtered summary or filter thresholds visible near the top. Do not silently turn `metadata.md` into a dump of every candidate.
   10. Use one row per unique candidate and keep repository/project/platform summary fields on that same row. Do not split papers/methods and repositories into separate metadata tables unless the user explicitly asks for a normalized database layout.
   11. In Markdown, omit machine-oriented or dense fields such as `type`, lab/organization, row-level uniqueness, raw repository URL, repository maturity code (`repo_status`), repository creation date, stars per month, computed popularity score, and `generation_mode` unless the user explicitly asks to show them. Keep a compact text `热门度` column in the human table when GitHub repository data is available, and keep the omitted machine fields in `metadata.json`.
   12. Do not use `优先级` as a Markdown table column by default. Encode priority by grouping the human catalog into compact subtables, while retaining `priority` in `metadata.json`.
   13. Reconcile discovery before admission. Every high-relevance paper, repository, dataset, or method named in scouting evidence must be copied into `scouting_evidence.candidate_leads` with its discovery query and source. Candidate admission must give each normalized lead exactly one disposition in `candidate_admission.scouting_dispositions`: `admit`, `reject`, `merge`, or `defer`, with a reason. A lead may be omitted from the final catalog only after an explicit `reject`, `merge`, or `defer`; mentioning it inside a free-form search-result sentence is not a disposition.
9. Prevent omission by searching variant axes:
   1. For every foundation or high-popularity method, search the base method name plus likely extension axes such as `panorama`, `360`, `equirectangular`, `fisheye`, `omnidirectional`, `video`, `dynamic`, `metric`, `scale`, `any view`, `any camera`, `robotics`, `driving`, and `Gaussian`.
   2. Search both directions: method-to-extension, for example `Depth Anything panorama`, and extension-to-method, for example `panoramic depth foundation model`.
   3. Use paper sources, project pages, GitHub repository search, and organization/repo searches to cross-check whether a variant is an independent method, a versioned member, a downstream wrapper, a benchmark, or only a demo.
   4. When the user hints that a missing variant may exist, treat that as a falsification signal and run targeted variant-axis searches before updating the catalog.
   5. Do not rely on title-only Gaussian/Splatting searches. Also search abstracts, README output schemas, project pages, and code symbols for `3D Gaussians`, `3DGS`, `Gaussian head`, `Gaussian Splatting head`, `splats`, `means`, `opacities`, `scales`, `quats`, `sh`, `novel view synthesis`, and `render novel views using 3D Gaussians`.
   6. For universal geometry or world-model routes, run additional queries with `universal 3D reconstruction`, `3D world reconstruction`, `geometric prediction`, `any-prior`, `prior prompting`, `multi-modal priors`, `world model`, `camera depth normals Gaussians`, `NVS`, and `3D Gaussians`, because these methods may expose GS only as one output head.
   7. For current foundation-model families, explicitly sweep both paper and repository sources for GS/NVS heads: `VGGT`, `DUSt3R`, `MASt3R`, `Fast3R`, `CUT3R`, `Depth Anything`, `MapAnything`, `Pi3`, `UniDepth`, `Pow3R`, `HunyuanWorld`, `HY-World`, `WorldMirror`, and major-lab organization pages. Record whether a hit is native model output, optional wrapper, downstream integration, or post-optimization-only feature.
   8. For relighting, shadow, visibility, ray tracing, renderer, PBR, or light-transport tasks, run a mandatory rendering-backend sweep in addition to method-title searches. Include both paper and repository queries for `secondary rays`, `shadow rays`, `Gaussian particles`, `3D Gaussian Ray Tracing`, `3DGRT`, `3DGUT`, `3DGRUT`, `hybrid rasterization`, `hybrid rendering`, `OptiX`, `Vulkan Gaussian Splatting`, `particle scenes`, `reflection refraction shadows`, `primary rays`, `secondary rays`, `distorted cameras`, and `rolling shutter` when relevant. This rule exists because backend papers may solve the user's shadow/visibility need without using `relighting` or `PBR` in the title.
   9. Classify rendering-backend hits by contribution rather than by title. A backend/framework can enter the method or backend-candidate pool when it is official or mature, preserves the target representation enough for the task, and directly exposes the needed renderer capability. A viewer, demo, asset layer, or API testbed belongs in `platform_tool` even when it implements shadows. A primitive-changing paper, for example a triangle route found during Gaussian-particle searches, should be kept as `reference` or `boundary_reference` unless the user accepts the representation change.
   10. For depth, pointcloud, geometry-prior, NVS-initialization, or feed-forward GS tasks, run a mandatory depth-capability sweep in addition to famous-family and output-name searches. Include paper and repository cross-products over `arbitrary-resolution`, `continuous-coordinate depth`, `neural implicit depth field`, `fine-grained depth`, `high-resolution depth`, `4K depth`, `depth sensor augmentation`, `depth completion`, `large viewpoint shift`, `fewer holes`, `depth to 3DGS`, `single-image 3D Gaussian`, `depth to point cloud`, and `video depth global point cloud`. These terms identify representation and downstream capability; do not require them all to appear in the title.
   11. Route depth-capability hits by verified output schema. A depth-first paper belongs in the point/depth/geometry catalog even when its title does not mention reconstruction. If its official code also has a pretrained direct Gaussian head that outputs Gaussian attributes or PLY without per-scene optimization, cross-reference it into the `FF-GS` catalog and state that the paper contribution is depth-first. If Gaussian output is only depth unprojection, visualization, or per-scene optimization, keep it as a geometry backbone or `INIT+OPT`, not direct `FF-GS`.
10. Expand collection rules from missed anchors:
   1. When the user identifies a missed paper, project, or repository, treat it as an evidence-bearing falsification of the current search rules, not as a one-off correction.
   2. Capture the missed anchor before editing catalogs: exact title, aliases, arXiv / venue dates, project page, repository, lab/organization, output representation, input assumptions, application framing, and phrases used by the authors.
   3. Diagnose why the old search rules missed it. Check whether the title avoided `Gaussian` / `Splatting`, whether the primary framing was `world model`, `video generation`, `robotics`, `driving`, `single-view to multi-view`, `novel trajectory`, `reconstruction-generation`, `sensor simulation`, or another adjacent phrase.
   4. Add at least one new query axis that would have found the anchor from a cold start. Prefer rules that combine route terms with representation or output terms, for example `"4D world model" "Gaussian Splatting"`, rather than only adding the method name.
   5. Search both paper and repository surfaces with the new axis: arXiv / paper search, project page text, GitHub repository search, README/API output schema, and code symbols when available.
   6. Record the anchor as a rule-learning case inside this skill or in a local research operation note, including the new query templates, expected hit type, classification caution, and the reason the rule is not over-broad.
   7. Validate the expanded rule immediately: show that at least one new query would retrieve the missed anchor and state which route it should enter or cross-reference. Do not promote the anchor into a method pool until the normal quality gate, method/platform separation, and metadata sync checks pass.
   8. Keep rule expansions conservative. A missed system paper may justify a new system / cross-reference search axis, but it does not prove all papers under that phrase belong in the core method pool.
   9. Rule-learning case: `3DGRUT / 3DGRT / 3DGUT` was missed in a relighting/shadow recomputation survey because the old queries focused on `relighting`, `PBR`, and `shadow decomposition`. The cold-start queries that recover it are `3DGRT 3DGUT 3DGRUT Gaussian`, `Gaussian Splatting secondary rays ray tracing shadows`, and `Gaussian particles ray tracing hybrid rasterization`. Expected hit type: backend-candidate or platform/tool, not automatically a relighting method. Classification caution: promote `nv-tlabs/3dgrut` because it is official, open-source, and supports secondary rays for shadows/reflections/refractions; keep `Vulkan Gaussian Splatting` as platform/tool; keep `RaySplats` as paper/backend reference when code maturity is not verified; keep `UTrice` as boundary reference because it changes primitives toward triangles.
   10. Rule-learning case: `InfiniDepth` was missed in a feed-forward point/depth/GS survey because candidate generation was anchored on `VGGT-like`, famous model families, metric depth, and panorama variants, while omitting resolution/representation/mechanism queries. A cold-start query `arbitrary resolution depth neural implicit field` retrieves arXiv 2601.03252 directly; supporting axes are `fine-grained 4K depth`, `continuous-coordinate depth`, `monocular depth novel view synthesis fewer holes`, and `single image depth 3D Gaussian`. Expected routing: P1 in point/depth/geometry because the paper's main contribution is continuous implicit depth; also cross-reference as `FF-GS` when official `inference_gs.py` is verified to predict means, harmonics, opacities, scales, and rotations and export PLY without per-scene optimization. Classification caution: a depth paper mentioning NVS is not automatically direct `FF-GS`; inspect the output code path first.
11. Track popularity and uniqueness:
   1. If a candidate has a GitHub repository, record stars, repository creation date, stars per month, and a popularity score.
   2. Use a reproducible score formula unless the user specifies another one. Default formula: `age_months = max(1, days_since_repo_created / 30.4375)`, `stars_per_month = stars / age_months`, `popularity_score = round(100 * (0.65 * log10(stars + 1) / log10(max_stars + 1) + 0.35 * log10(stars_per_month + 1) / log10(max_stars_per_month + 1)))`.
   3. Record the scoring date and compute `max_stars` / `max_stars_per_month` over the currently verified repository catalog.
   4. In Markdown, express popularity as one text field: `star数/表格中最大star数；记录年月；项目距记录时间月数差值`, for example `1234/5678；2026-06；8.2个月`. Use `N/A；记录年月；N/A` when no repository or creation date is verified.
   5. Evaluate uniqueness against the current mainstream frameworks for the active route, not against older historical baselines. Historical importance, ancestry, or being an early representative does not by itself count as uniqueness.
   6. Do not mark a generic capability as unique when current mainstream models already cover it, for example single-image point map/point cloud output or ordinary monocular depth. A useful engineering feature, such as camera FoV estimation, is not a uniqueness exception unless it materially changes the route compared with current mainstream options.
   7. Treat speed, sharpness, boundary quality, or similar performance claims as uniqueness only when they are explicitly compared against the current mainstream models in the active catalog. Claims validated only against older prior work should stay as baseline/status notes, not uniqueness exceptions.
   8. Treat optional-input or multimodal-input support as unique only after checking whether current mainstream models support the same input combination. For example, a framework-level interface that supports image + calibration/pose/depth combinations and reconstruction/completion/registration tasks may be distinct from image-only models, but the note must say the uniqueness is interface-level rather than output-level.
   9. In JSON, add a compact `uniqueness` note for each method or platform. Most entries may legitimately say they have no current uniqueness because newer models subsume them.
   10. In Markdown, do not keep a row-level `独特性` column by default. If only a few entries remain distinct under the current-mainstream comparison, list those entries in a short note below the catalog tables; if none remain distinct, omit the note.
12. Use Chinese for research prose by default:
   1. Use Chinese for explanations, status notes, route judgments, and table prose.
   2. Keep established method names, repository names, field names, conference names, formulas, and technical terms in English when translation would reduce precision, for example `4DGS`, `Gaussian`, `deformation field`, `feed-forward`, `metadata.json`, `CVPR`, and `stars/month`.
   3. Avoid English filler phrases such as `official candidate`, `pending verification`, or `watchlist` in human-facing Markdown when a clear Chinese equivalent works. Machine fields in JSON may keep stable codes such as `P0`, `G1`, `repo_status`, and `pool_status`.

## Mandatory Flow Control

This skill is stage-gated. The agent must not treat a research run as complete, or advance to the next stage, until the current stage has a manifest and the local guard has passed or the user explicitly overrides the guard.

Use the flow-control files under the active research output directory:

1. `.research_flow/run_state.json`: current stage, stage status, timestamps, and guard results.
2. `.research_flow/stage_manifests/<stage>.json`: evidence record for each stage.

Use the helper scripts in this skill directory:

1. `scripts/research_flow_next.py`: initialize a run and advance between stages.
2. `scripts/research_flow_guard.py`: validate the required evidence and output files for a stage.
3. `scripts/arxiv_fetch.py`: search arXiv with local disk cache, cross-process throttling, retry/backoff for 429/503, arXiv abstract-page fallback for ID lookups, and OpenAlex fallback for keyword searches.

Default stage order:

1. `anchor_scope`: lock the research question, target route, output directory, time windows, and candidate boundaries.
2. `operation_guide`: define search batches, sources, variant axes, pre-search query-axis expansion, dedup rules, quality gates, and completion criteria.
3. `scouting_evidence`: record paper searches, repository searches, recent-window checks, mature-framework checks, variant-axis sweeps, reverse output-representation sweeps, and checked-negative findings.
4. `frontier_omission_audit`: before admission, record current-year / previous-year top-venue sweeps, official-source checks, recent-month queries, repository-created-date sweeps, source failures/fallbacks, staleness diagnosis, premature-convergence risk, missing-anchor replay checks, and the planned Markdown display filter. For every non-trivial stage-gated run, write the evidence to `frontier_omission_audit.md`.
5. `candidate_admission`: classify each candidate as method, geometry backbone, `INIT+OPT` system, platform/tool, paper lead, reference, extra lead, or non-fit before admission; include an official-source matrix for P0/P1 and other displayed candidates.
6. `metadata_consolidation`: synchronize `metadata.json` and `metadata.md`; retrieve and store compact abstract innovation points; record platform/tool repo-to-paper association; keep JSON as the full catalog and Markdown as the compact filtered display view unless an explicit full-display override is recorded.
7. `analysis_notes`: create and register task-specific analysis files only when needed; otherwise record why this stage is not applicable.
8. `final_report`: summarize coverage, remaining omissions, recent results, frontier results, official-source status, mature frameworks, Markdown display filtering, staleness/saturation diagnosis, variant axes searched, and recommended next phase.

Optional branch stage:

1. `collection_rule_expansion`: use when the user identifies a missed anchor. Complete this branch before finalizing the active candidate pool.

Minimum operating rule:

1. At the start of a non-trivial research run, run `python CODEX_HOME/skills/fjn-research-flow/scripts/research_flow_next.py init --run <output_dir>` or create equivalent `.research_flow` files manually.
2. Before entering a stage, make sure its manifest exists. Use the template generated by `research_flow_next.py` or copy `templates/stage_manifest.json`.
3. Before leaving a stage, run `python CODEX_HOME/skills/fjn-research-flow/scripts/research_flow_guard.py --run <output_dir> --stage <stage> --write-state`.
4. If the guard fails, repair the missing evidence or outputs in that same stage before advancing.
5. If a source is unavailable because of rate limits, access failure, or missing public metadata, record the failure and the fallback source in the stage manifest. Do not silently count a failed search as coverage.
6. If the user asks for a quick answer rather than a full research run, state that the stage-gated workflow is being skipped and why.

arXiv access rule:

1. For arXiv searches in this skill, use `python CODEX_HOME/skills/fjn-research-flow/scripts/arxiv_fetch.py search "<query>" --max <N>` instead of raw `curl`, browser scraping, or ad hoc `urllib` calls.
2. For single-paper checks, use the same command with an arXiv ID, for example `python CODEX_HOME/skills/fjn-research-flow/scripts/arxiv_fetch.py search "2604.13333" --max 1`. If the export API is rate-limited, the helper may return `metadata_source: arxiv_abs_html_fallback`.
3. Keep the default cache unless the user explicitly needs a live refresh. Use `--fresh` sparingly because it bypasses fresh cache and increases 429/503 risk.
4. Prefer a repo-local ignored contact file over environment variables. Put one email or contact URL on the first non-comment line of `CODEX_HOME/skills/fjn-research-flow/.local/arxiv_contact.txt`; `.local/` is ignored by this skill directory's `.gitignore`. The helper also accepts `--contact-file <path>` for another local file. Do not commit personal email addresses unless the user explicitly wants a shared team contact in version control.
5. Environment variables `FJN_ARXIV_CONTACT` or `ARXIV_CONTACT` remain last-resort fallbacks only. When a contact is configured, requests include it in the User-Agent and, for OpenAlex fallback, in the `mailto` field when it is an email address.
6. If the helper returns fallback metadata, record the fallback source in `scouting_evidence.fallbacks_used` or `frontier_omission_audit.source_failures`. If all arXiv paths fail, continue with OpenAlex, Semantic Scholar, official venue pages, project pages, and repository README/BibTeX; mark arXiv as an access limitation rather than a negative search result.

## Standard Workflow

Run this workflow through the Mandatory Flow Control stages above. The checklist below defines the research work inside those stages.

1. Anchor the stage
   1. Read the current plan file.
   2. Identify the active phase and requested output directory.
   3. If the phase is strategic, do not start detailed research until an operation guide exists.
2. Create or update the operation guide
   1. Define search batches, information sources, record fields, dedup rules, and completion criteria.
   2. Before running any real paper/repository query, complete `operation_guide.query_axis_expansion`. Start from the anchored research question and expand it into problem terms, representation/output terms, mechanism terms, application/domain terms, source-surface terms, negative or boundary terms, cross-product query templates, narrowness risks, and final query axes. This is the deliberate thinking step that prevents one narrow keyword family from controlling the search.
   3. Build final query axes from combinations, not only synonyms. Combine at least one route/problem term with at least one representation/output or mechanism term, and include reverse searches such as output-to-method, application-to-method, and source-surface-to-method when relevant.
   4. Write a short `pre_search_review` that states why the axes are broad enough, what they still may miss, and which boundary terms will keep the pool from becoming over-broad. Do not enter `scouting_evidence` until this review and the final query axes are recorded.
   5. Make recent-result checks explicit.
   6. Make mature-framework checks explicit.
3. Execute scouting
   1. Search papers and repositories in parallel where possible. Use `scripts/arxiv_fetch.py` for arXiv batches so repeated / concurrent agent searches share cache and respect throttling.
   2. Use paper-to-repo and repo-to-paper cross-validation.
   3. Apply the paper quality gate before writing final candidate files.
   4. Run an anti-omission variant sweep for each P0/P1 seed method and for any variant hinted by the user.
   5. For foundation geometry, universal reconstruction, or world-model candidates, inspect the abstract and official README/API output format for direct Gaussian outputs before deciding the route. A model that returns `predictions["splats"]` or equivalent Gaussian attributes should not be missed because its title is framed as point/depth/geometry reconstruction.
   6. For feed-forward GS routes, run at least one output-representation reverse sweep before finalizing the candidate pool; use the terms in Core Principle 9 rather than only exact method names.
   7. Search survey papers, review papers, reading lists, and summary blogs as auxiliary reference sources. Record them in a separate reference note, not in metadata.
   8. Record whether variant hits are independent methods, versioned releases, native GS/NVS heads, downstream wrappers, benchmarks, demos, post-optimization-only features, or false positives.
   9. Record candidates into compact markdown files.
   10. If the scouting run is responding to a known missed anchor, run the expanded-rule workflow in Core Principle 10 before finalizing the candidate pool.
   11. Before leaving scouting, extract every high-relevance named hit from search-result prose into `scouting_evidence.candidate_leads`. Use one record per canonical method or project with `name`, `source`, `relevance`, and `discovery_query`; aliases belong in the same record rather than becoming duplicate leads.
4. Run frontier omission audit before candidate admission
   1. Check current-year and previous-year top venue surfaces that are relevant to the route, such as CVF OpenAccess / proceedings, OpenReview, SIGGRAPH / ACM, ECCV / ICCV, NeurIPS / ICML / ICLR pages, workshop pages, project pages, and repository README/BibTeX.
   2. Run recent-month paper queries and repository `created:` sweeps with route-specific synonyms. Do not let high-star historical repositories hide low-star but fresh accepted work.
   3. Build an official-source matrix for candidates that will appear in P0/P1 tables or in `metadata.md`: venue/date source, project source, repository source, and checked-negative notes when a source is absent.
   4. Write a staleness diagnosis before making claims such as `no new methods`, `direction saturated`, or `field reached upper limit`. The diagnosis must distinguish true negative evidence from source/API failure.
   5. Decide the `metadata.md` display mode and filter thresholds before writing the Markdown table; record this plan in the manifest.
   6. Reconcile `scouting_evidence.candidate_leads` against `candidate_admission.scouting_dispositions` before admitting candidates. Do not advance while any lead lacks exactly one explicit disposition, even if the lead appeared only in an aggregated search-result sentence.
5. Consolidate metadata (mandatory)
   1. Create or update a catalog-only `metadata.md` after candidate lists are updated.
   2. Merge candidate papers, candidate repos, projects, methods, integration platforms, benchmarks, recent watchlist items, and newly discovered-but-not-yet-admitted leads into the JSON `catalog`. Build the Markdown catalog as a compact display view, using priority-derived subtables for readability.
   3. By default, build Markdown as a filtered display view with separate code-backed and no-code rules. Treat entries with verified released code or an inspectable repository/codebase as code-backed. For code-backed entries, keep a candidate when its arXiv/preprint date is within 18 months of the scoring/current research date, or its formal acceptance/publication date is within 12 months, or its visible popularity reaches at least half of the current catalog maximum (`stars >= 0.5 * max_stars`). For no-code, code-not-yet-released, closed-source, or project-page-only entries, keep a candidate only when its formal conference/journal acceptance or publication is within 6 months of the scoring/current research date; arXiv-only recency is not enough for these rows. If only year-month granularity is known, compare by month and include the cutoff month. Keep entries that satisfy none of these gates only in JSON unless the user asks to display them. For displayed no-code entries, state the missing repository/code status directly in the human table.
   4. Record `metadata_consolidation.markdown_display` in the stage manifest: display mode, code-backed gate, no-code gate, popularity gate, full catalog location, filtered-out count, and override reason when full display is requested. This is a hard validation field, not a prose-only preference.
   5. Record `metadata_consolidation.abstract_innovation` in the stage manifest: JSON field name, source field name, status field name, source policy, missing-abstract policy, required Markdown column, exact Markdown column list, and removed legacy columns. This is a hard validation field, not a prose-only preference.
   6. Record `metadata_consolidation.platform_paper_association` in the stage manifest: association field, source field, status field, required platform/tool types, allowed statuses, checked-source policy, and no-paper claim policy. This guard exists because platform/tool categorization is not evidence that no paper exists.
   7. For each catalog entry, retrieve the paper abstract or closest official source and write a compact `abstract_innovation` summary. If the abstract cannot be found, say which official source or title/metadata fallback was used and keep the mechanism conservative.
   8. For each platform/tool catalog entry, run a repo-to-paper linkage check over README, project page, Paper/arXiv/DOI/BibTeX links, and cited published-work dependencies before writing `repo-only` or no-formal-paper language. Store the result in `paper_association`, `paper_association_source`, and `paper_association_status`.
   9. For each Markdown entry, include at minimum: name, arXiv/formal date, venue/journal, core idea or core output, input assumptions, text popularity field when available, and `摘要创新点`. Use the subtable title to express priority grouping instead of a per-row `优先级` column. Do not show `生成模式` or status/remarks in the default human table.
   10. Mark unknown fields explicitly as `pending verification`; never infer missing publication metadata without evidence. If a targeted venue search finds no formal publication venue, write a concise checked-negative note such as `formal venue not found` rather than leaving the entry as arXiv-only.
   11. Create or update `metadata.json` as a machine-readable canonical catalog. JSON should retain full machine fields, including priority, type, lab/organization, row-level uniqueness, raw repository/project URL, stars, repository creation date, stars per month, repository maturity, popularity score, `generation_mode`, `status_notes`, `abstract_innovation`, abstract source/status fields, and platform `paper_association` fields, even when the Markdown display filters rows out.
   10. For universal models with multiple output heads, keep `core_output` explicit about the Gaussian output and list the broader outputs in `status_notes` or a dedicated report. If optional post-optimization exists, classify the feed-forward Gaussian output as `FF-GS` and record the optimization path as optional refinement rather than changing the generation mode.
   11. Move non-catalog material into separately named Markdown files, for example `lineage_notes.md`, `taxonomy_notes.md`, `application_notes.md`, `limitations.md`, or `route_recommendations.md`.
   12. If the research question needs a conclusion such as whether feed-forward support extends to 4D, record that conclusion in an analysis note and link to it from the catalog instead of embedding the analysis inside `metadata.md`.
   13. If popularity fields are present, store the scoring formula and scoring date in both `metadata.md` and `metadata.json`.
   14. When the user asks for deep per-paper innovation research over a metadata catalog, expand the compact metadata `abstract_innovation` entries into a separate `method_innovation_notes.md`. Cover every `metadata.json.catalog` entry, distinguish abstract-grounded facts from inferred implications, and note any entry whose full abstract could not be found.
   15. When the user asks for a technical development route or timeline, write a separate `technical_evolution.md`. Base it on publication dates, generation mode, input assumptions, and per-paper innovation axes; keep `FF-GS` and `INIT+OPT` routes explicitly separated.
   16. When these analysis documents are created, link them from the Markdown catalog intro when useful and register them in `metadata.json.analysis_files`.

## Metadata Table Template

Use one catalog section in `metadata.md` with one row per displayed candidate. Markdown is the human-readable view, so keep it compact: split the catalog into priority-derived subtables, show `发表机构` from `metadata.json.lab_org`, show text `热门度`, and include `摘要创新点` as the human-facing evidence/innovation column. Omit `优先级`, `类型`, `生成模式`, row-level `独特性`, raw repository links, repository maturity code, repository creation date, stars per month, computed popularity score, and operational status notes as table columns. Keep those fields in `metadata.json`.

Default Markdown display filter: use separate gates for code-backed and no-code entries. Code-backed entries are candidates with verified released code or an inspectable repository/codebase. Show a code-backed entry when it satisfies at least one of three display-priority gates: arXiv/preprint date within 18 months of the scoring/current research date, formal acceptance/publication date within 12 months of that date, or visible popularity at least half of the current catalog maximum (`stars >= 0.5 * max_stars`). For no-code, code-not-yet-released, closed-source, or project-page-only entries, show the entry only when it has formal conference/journal acceptance or publication within 6 months of the scoring/current research date; arXiv-only recency is not enough. If only year-month granularity is known, compare by month and include the cutoff month. State the active arXiv cutoff, code-backed publication cutoff, no-code formal publication cutoff, and popularity threshold in the Markdown intro. Keep entries that satisfy none of these gates only in `metadata.json`, unless the user asks for a full watchlist or historical view.

Task-specific extra columns are allowed only when the user explicitly asks for them. Keep `generation_mode` in `metadata.json`; do not show `生成模式` in the default Markdown table. The default human table should replace old `状态 / 备注` prose with an abstract-grounded `摘要创新点` column.

For every catalog entry, append `abstract_innovation`, `abstract_innovation_source`, and `abstract_innovation_status` in `metadata.json`. Prefer official abstract sources; use project pages or repository README only as marked fallbacks, and mark title-only summaries as abstract pending.

The Markdown `热门度` value format is `star数/catalog最大star数；记录年月；项目距记录时间月数差值`. Compute the month difference using the same month basis as `stars_per_month`, normally `days_since_repo_created / 30.4375`, rounded compactly for reading. Use the catalog `max_stars` from `metadata.json.popularity_scoring` for both display and the half-popularity display gate, so the threshold does not shift when Markdown rows are filtered.

### 1.1 重点候选（P0 / P1）

| 名称 | 日期 / venue | 发表机构 | 核心输出 | 输入假设 | 热门度 | 摘要创新点 |
| --- | --- | --- | --- | --- | --- | --- |
| ExampleMethod | arXiv 2026-01; CVPR 2026 | Example University / Example Research | point map / depth / camera | one/few/many views | 1234/5678；2026-06；8.2个月 | 摘要显示其直接预测 Gaussian attributes，并通过跨视角几何约束提升 NVS 稳定性；摘要不可得时必须标注 fallback。 |

### 1.2 扩展与历史参照（P2）

| 名称 | 日期 / venue | 发表机构 | 核心输出 | 输入假设 | 热门度 | 摘要创新点 |
| --- | --- | --- | --- | --- | --- | --- |
| ExampleBench | arXiv 2026-02 | Example Institute | benchmark dataset | target domain | N/A；2026-06；N/A | 摘要待补；当前仅能确认其是面向目标域的数据集/基准线索，不能据此推断方法机制。 |

### 1.3 当前仍有相对独特价值的方法

Only include this note when a small number of candidates remain meaningfully distinct relative to the current mainstream route. Compare against current mainstream frameworks, not historical predecessors. If no candidate remains distinct, omit this subsection.

The JSON mirror should use a single top-level `catalog` array for the full candidate set. JSON keeps the full machine-readable fields, including `priority`, `type`, `lab_org`, `uniqueness`, `repo_project`, `stars`, `created_at`, `stars_per_month`, `repo_status`, `popularity_score`, `generation_mode`, `status_notes`, `abstract_innovation`, `abstract_innovation_source`, and `abstract_innovation_status`. Platform/tool entries must additionally keep `paper_association`, `paper_association_source`, and `paper_association_status`. Do not use separate arrays such as `papers_methods` and `repositories_projects_platforms` for the same candidate set. When Markdown is filtered, validate that Markdown names are an ordered subset of JSON `catalog` names rather than requiring exact row-count equality.
5. Grade candidates
   1. Assign P0/P1/P2 according to relevance to driving simulation.
   2. Assign G0 when the method has enough public evidence to remain in the candidate pool.
   3. Mark G1 potential only when code, weights, demo, or clear instructions suggest practical reproducibility.
   4. Do not let recency alone promote a paper into G0; unknown arXiv-only work stays out unless it passes the quality gate.
6. Summarize
   1. Report coverage by route.
   2. Highlight recent 1-2 month results.
   3. Highlight mature frameworks from the last year.
   4. State which variant axes were searched and which likely omissions remain.
   5. Recommend what should enter the next phase.

## Candidate Usability Screening

Use this phase when the user already has a broad literature/repository catalog and wants to narrow it into methods or repositories that are genuinely worth trying for a concrete target. Treat this as an extension of the research flow, not a separate skill: it depends on the same catalog, metadata, method/platform separation, maturity grading, and omission checks.

1. Start from a target contract before comparing candidates:
   1. Required input: images, video, known/unknown pose, intrinsics, depth, LiDAR, masks, text, or other priors.
   2. Required output: direct 3DGS/Gaussian parameters, point map, depth, camera, mesh, semantic assets, simulator-ready scene, or optional export.
   3. Operating limits: GPU class, memory budget, latency or throughput target, scene scale, batch/sequence length, license, and deployment environment.
   4. Evaluation target: reconstruction, novel-view synthesis, geometry quality, editing, driving simulation, data generation, or downstream integration.
2. Type every candidate before scoring it:
   1. Method body: directly solves the target route.
   2. Geometry backbone: useful frontend but not the final target artifact by itself.
   3. `INIT+OPT` system: initializes or refines through optimization and must not be mixed with pure feed-forward timing.
   4. Platform/tool: useful engineering base, dataset, renderer, simulator, or pipeline component.
   5. Paper lead: interesting but not currently usable because code, weights, license, or instructions are missing.
   6. Non-fit: cannot satisfy the target contract without changing the problem.
3. Apply hard gates before soft scoring:
   1. No public code or weights means paper lead, not a usable candidate.
   2. License incompatibility excludes the candidate from industrial-use tiers.
   3. Missing required output excludes the candidate from same-tier comparison; record it as a backbone or adjacent lead instead.
   4. Post-optimization must be separated from pure feed-forward output in timing, quality, and resource claims.
   5. Known-pose, calibrated-camera, fixed-view-count, or domain-specific assumptions must be treated as constraints, not small implementation details.
   6. Unsupported long-sequence, large-scene, or export paths must be recorded even when another branch of the project supports them.
4. Compare input contracts as relative engineering cost, not as a flat feature list. State which method buys flexibility by learning pose/depth/scale, which method requires external preprocessing, and which method becomes easier or more reliable when given calibrated inputs.
5. Compare principles against the target bottleneck. Tie architectural differences to likely effects, such as dense patch features, cross-view attention, depth/ray representation, Gaussian head design, scale alignment, camera conditioning, chunking, or refinement.
6. Use an evidence ladder and mark comparability:
   1. Strong evidence: paper tables, official benchmark scripts, official model/API docs, released weights, and reproducible commands.
   2. Medium evidence: official issues/discussions, maintainer replies, third-party reproducibility reports, integrations, and independent demos with clear settings.
   3. Weak evidence: social demos, screenshots, unverified claims, or metrics without protocol details.
   4. Never compare numbers as if they are same-protocol when dataset, view count, resolution, hardware, optimization steps, or output mode differ.
7. Evaluate engineering usability explicitly: install path, dependency age, API stability, batch support, export format, memory behavior, speed, model size, failure recovery, issue activity, maintainer responsiveness, and whether community users report the same failure modes.
8. Record failure modes with sources. Prefer official limitations and public issue patterns over speculative criticism; distinguish model limitations from user setup errors when evidence allows.
9. Tier the remaining candidates for action:
   1. Immediate trial: passes hard gates and has enough evidence for a short reproduction run.
   2. Focused re-test: promising but one assumption, metric, export path, or resource claim needs direct local validation.
   3. Watch: relevant but blocked by missing release, immature repo, license, or insufficient independent evidence.
   4. Exclude: fails the target contract or hard gates.
10. Every recommendation must state evidence strength and missing validation. If no same-table benchmark exists, say so directly and avoid over-ranking from incompatible metrics.

## Collection Rule Expansion

Use this phase when the user says a relevant paper or repository was missed, asks to `扩展收集论文规则`, or provides a new anchor that should have been found by the scouting workflow. The goal is to improve future collection behavior, not only to add the current anchor.

1. Anchor facts:
   1. Record the exact missed item and all author-facing names: title, project name, repository name, model/checkpoint name, and common abbreviations.
   2. Record official source surfaces: arXiv / proceedings, project page, GitHub, Hugging Face / ModelScope, lab blog, and workshop page when relevant.
   3. Record route-relevant phrases from the authors, especially output representation, generation mode, input assumptions, applications, and claims such as `pose-free`, `feed-forward`, `world model`, `novel trajectory`, `single-view to multi-view`, `4D reconstruction`, `Gaussian Splats`, `3DGS`, or `4DGS`.
2. Failure diagnosis:
   1. Identify which old query family failed: title-only GS search, method-name search, paper-only search, repo-only search, recent-only search, top-venue-only search, or missing adjacent-domain terms.
   2. Identify whether the item was hidden by classification ambiguity: method vs platform, 3DGS vs 4DGS, reconstruction vs generation, driving-specific vs general world model, or feed-forward vs initialization plus optimization.
3. New rule design:
   1. Add phrase-level query templates that would retrieve the anchor without knowing its name.
   2. Add source-level sweeps when needed, such as workshop award pages, model hub collections, organization repositories, or project-page backlinks.
   3. Add classification cautions so future runs include the item but do not over-promote it.
4. Immediate validation:
   1. Run at least one paper search and one repository/project search with the new terms.
   2. State whether the anchor belongs in the active route as a method, cross-reference, platform, paper lead, or extra lead.
   3. Update metadata only after the rule and classification both pass the normal quality gate.

### Learned Omission Rules

#### ViShadow silent-drop anchor, added 2026-09-09

Missed item: `ViShadow: Video Instance Shadow Detection Under the Sun and Sky`, arXiv 2211.12827, IEEE TIP 2024, official repository `HarryHsing/Video-Instance-Shadow-Detection`.

Failure mode: the paper search did retrieve `ViShadow`, but the hit was embedded inside a free-form `result` sentence with LISA/SSIS/FastInstShadow. The workflow checked search breadth and frontier sources but did not reconcile named scouting hits against candidate admission. ViShadow therefore disappeared before the official-source matrix, metadata catalog, and final report despite directly matching shadow-object association and light-direction estimation.

New prevention rule: every high-relevance named hit must enter `scouting_evidence.candidate_leads`, and every lead must receive exactly one `admit`, `reject`, `merge`, or `defer` record in `candidate_admission.scouting_dispositions`. The guard compares normalized names across these two lists and blocks silent disappearance. Free-form search summaries remain supporting evidence, not the candidate ledger.

Cold-start query axes that retrieve ViShadow without knowing its name:

- `video instance shadow detection object shadow association`
- `shadow object pair tracking video light direction estimation`
- `SOBA-VID shadow object association`
- `semi-supervised video shadow object instance tracking`
- repository search: `video instance shadow detection association masks pretrained weights`

Expected routing: P1 method for video or multi-frame vehicle-shadow association, with an official code repository, released `model_final.pth`, and a demo producing per-frame shadow-object association masks. It may also inform single-frame experiments because Stage I is trained on labeled SOBA images, but the released model's principal contract is online video inference.

Classification caution: do not merge ViShadow with `ViSha` or `Triple-cooperative Video Shadow Detection`. `ViSha` is a video-level binary shadow dataset/method family without object-shadow instance association; `ViShadow` is a video instance shadow framework using SOBA image supervision plus SOBA-VID temporal training. Also do not call it a single-frame replacement merely because its first stage consumes labeled images.

#### NeoVerse anchor, added 2026-06-22

Missed item: `NeoVerse: Enhancing 4D World Model with in-the-wild Monocular Videos`, arXiv 2026-01, CVPR 2026 Highlight, official repo `IamCreateAI/NeoVerse`.

Failure mode: exact `4DGS` or `Gaussian Splatting` title searches can miss papers whose primary framing is `4D world model`, `novel-trajectory video generation`, or `in-the-wild monocular videos`, even when the method contains a pose-free feed-forward 4DGS reconstructor and Gaussian Splats are a central intermediate representation.

New query axes for 4DGS / world-model scouting:

- `"4D world model" "Gaussian Splatting"`
- `"4D world model" "Gaussian Splats"`
- `"pose-free feed-forward 4DGS"`
- `"novel-trajectory video generation" Gaussian`
- `"monocular video" "4D reconstruction" "Gaussian"`
- `"single-view to multi-view" "Gaussian Splatting"`
- `"target trajectory" "Gaussian Splats" video generation`
- GitHub search: `4D world model Gaussian SplatRenderer`, `novel trajectory Gaussian Splats`, `feed-forward 4DGS reconstruction`.

Source sweeps to add when this axis is active:

- project pages and READMEs for `reconstructor`, `Gaussian Splats + camera poses`, `target-trajectory rendering`, `degraded rendering`, `VideoWorldModel Workshop`, `CVPR Highlight`, `single-view to multi-view`, `bullet time`, `camera control`, `driving`, and `robotics`.
- model hubs for checkpoints released under the method name, because these systems may release weights before a stable package or paper-code tag.

Classification caution: NeoVerse belongs in a 4DGS catalog as a `P2 system trend / cross-reference` unless the active task is explicitly about 4D world models. It may cross-reference feed-forward GS because it includes pose-free feed-forward 4DGS reconstruction, but it should not be promoted into the core 4DGS representation/optimization trunk or driving-specific method pool without route-specific evidence.

#### PBR-GS frontier anchor, added 2026-06-24

Failure mode: broad `PBR Gaussian Splatting`, `inverse rendering 3DGS`, and star-sorted GitHub searches can over-select 2023-2024 inverse-rendering / relighting methods and miss newer accepted work whose titles emphasize scattering, shadow, reflection/transmission, thermal infrared, hybrid path tracing, simulator-ready assets, or intrinsic decomposition rather than generic `PBR`.

New query axes for PBR / inverse-rendering / relightable GS scouting:

- `Gaussian Splatting scattering shadow CVPR 2026`
- `Gaussian Splatting reflection transmission CVPR 2026`
- `thermal infrared Gaussian Splatting radiative transfer`
- `hybrid path tracing Gaussian Splatting`
- `physically based Gaussian assets simulation`
- `intrinsic decomposition Gaussian Splatting CVPR 2026`
- `relightable Gaussian Splatting ICLR 2026`
- GitHub search with route terms plus `created:>=<current-year>-01-01`, for example `Gaussian Splatting relighting created:>=2026-01-01`.

Source sweeps to add when this axis is active:

- CVF OpenAccess / proceedings pages for CVPR, ICCV, and ECCV current-year and previous-year papers.
- OpenReview accepted-paper/forum pages for ICLR, NeurIPS, and ICML when relevant.
- Project pages and repository README/BibTeX for venue claims, because aggregators may lag official acceptance metadata.
- README keywords for `scattering`, `shadow`, `reflection`, `transmission`, `thermal`, `radiative`, `path tracing`, `intrinsic`, `material`, `BRDF`, `relighting`, `PBR`, and `simulation`.

Classification caution: ordinary RGB inverse-rendering / relighting may be crowded, but that does not justify concluding the route is saturated until the frontier audit covers the adjacent physical-effect axes above. Platform or renderer work should remain separate from method candidates unless it proposes a route-relevant PBR/GS representation or learning method.

## Output Pattern

For a step1 quick-scouting run, write results under the requested `run/step1/` folder:

1. `.research_flow/run_state.json`: stage state and guard history.
2. `.research_flow/stage_manifests/<stage>.json`: per-stage evidence manifests.
3. `candidate_papers.md`: compact candidate paper/method list.
4. `candidate_repos.md`: compact repository and maturity list.
5. `recent_watchlist.md`: latest 1-2 month papers/repos/projects.
6. `step1_summary.md`: P0/P1/P2 and G0/G1-potential summary.
8. `frontier_omission_audit.md`: current/previous-year frontier checks, official-source matrix summary, recent-query and repository-created sweeps, source failures/fallbacks, staleness diagnosis, and Markdown display-filter plan.
9. `metadata.md`: catalog-only metadata across papers, repositories, projects, methods, integration platforms, watchlist items, and extra leads. This is a filtered human-readable display by default.
10. `metadata.json`: canonical full catalog for scripts and downstream tooling.
11. Topic-specific analysis notes as needed, such as `lineage_notes.md`, `taxonomy_notes.md`, `application_notes.md`, `limitations.md`, or `route_recommendations.md`.
12. `method_innovation_notes.md` when the task asks for deep per-paper innovation research over the metadata catalog. It should cover every `metadata.json.catalog` entry and summarize abstract-grounded problem, innovation, technical mechanism, input assumptions, and caveats.
13. `technical_evolution.md` when the task asks for a chronological technical route. It should combine a timeline table with route-level synthesis across pose assumptions, geometry priors, architecture, robustness, efficiency, compression, long-sequence handling, and semantic outputs when relevant.
14. `survey_and_blog_notes.md` when survey papers, review papers, reading lists, or summary blogs are used as reference material. This file is a reference note, not a metadata catalog.
15. `hot_method_evolution.md` when the task asks for historical popular-method evolution or when popularity scoring materially affects route choices.
16. `candidate_screening_notes.md` when the task asks to narrow an existing catalog into usable papers or repositories. Include the target contract, candidate typing, hard-gate results, comparable evidence, usability risks, action tiers, and missing validation.

## Quality Bar

1. Every P0 route must be checked across paper sources, repository sources, and recent-result sources.
2. Recent items without code should be kept in the watchlist only if they pass the paper quality gate.
3. One-year mature frameworks should be elevated for later reproduction even if they are not the newest papers.
4. Do not include long abstracts, raw search dumps, repeated links, or low-confidence arXiv-only papers unless they change the routing decision and pass the quality gate.
5. Do not put narrative analysis into `metadata.md`; keep it in a named analysis file and keep `metadata.json` synchronized with catalog entries.
6. Do not stop at searching only the exact method name when the method is a foundation model. Always run at least one variant-axis sweep before declaring coverage complete.
7. Popularity is not quality by itself. Use it as an engineering-priority signal together with paper quality, repository maturity, current-mainstream uniqueness, and fit to the user's route.
8. Survey papers, review papers, reading lists, and summary blogs may support coverage checks, but they must not appear as catalog entries unless the user explicitly asks for a bibliography catalog.
9. For `method_innovation_notes.md`, validate that every `metadata.json.catalog` name appears in the document. If an abstract is unavailable, say which official source was used instead and keep the claims conservative.
10. For `technical_evolution.md`, validate that the document distinguishes direct `FF-GS` from `INIT+OPT` and covers both chronological stages and innovation axes rather than only listing papers.
11. Before declaring a feed-forward GS catalog complete, run at least one omission check over universal geometry / world reconstruction terms and verify whether any high-signal result directly outputs 3D Gaussians. If a previous submission was rejected but an official conference virtual page or proceedings page confirms later acceptance, record both facts carefully and use the final accepted venue in metadata.
12. For `candidate_screening_notes.md`, validate that every recommended candidate passed the target contract and hard gates, and that every metric comparison carries enough protocol context to be auditable.
13. Before any scouting search, `operation_guide.query_axis_expansion` must be filled and guard-validated. A non-empty `variant_axes` list alone is not enough; the manifest must record the expanded problem, representation/output, mechanism, application/domain, source-surface, boundary, cross-product, narrowness-risk, and final-query-axis fields.
14. For collection-rule expansion, validate that the new query axis would retrieve the missed anchor and record the classification caution that prevents over-broad promotion.
15. Do not finalize from an old-looking candidate pool without a frontier omission audit. If most displayed candidates are older than the route's current frontier window, either find current accepted/recent work or write a checked staleness diagnosis backed by official-source and recent-query evidence.
16. Do not trust aggregator venue/date fields for P0/P1 rows when official sources are available. Official proceedings, OpenReview/forum pages, project pages, repository README/BibTeX, and publisher pages override aggregator metadata.
17. `metadata.md` must not silently display every JSON candidate. The manifest must record display mode, cutoff gates, popularity threshold, filtered-out count, and any full-display override reason.
18. The final report must state frontier results, official-source status, Markdown display filtering, staleness/saturation diagnosis, and completion blockers checked. A plausible summary without these checks is incomplete.
19. For stage-gated runs, do not advance or finalize until `research_flow_guard.py --stage <stage>` passes for the current stage, or until the final response explicitly says which guard failed and why the user-requested shortcut overrides it.
20. For schema v2 runs, the candidate-admission guard must pass the scouting-lead disposition reconciliation. A frontier audit cannot compensate for a named high-relevance hit that was discovered but never admitted, rejected, merged, or deferred.