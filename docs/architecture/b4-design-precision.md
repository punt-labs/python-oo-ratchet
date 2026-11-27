# B4: precision of the design rules (PL-1716)

How often each advisory `design` rule is right, measured on the four adopter
repositories, and what that decides.

## Method

- Scanned read-only with `oo-ratchet design <package> --json` at the checkouts
  under `~/Coding/punt-labs/`: `vox/src/punt_vox` (632 files), `quarry/src/quarry`,
  `lux/src/punt_lux`, `z-spec/src/punt_zspec`. Each repository's own
  `[tool.oo-ratchet.layers]` table was used (found from the nearest
  `pyproject.toml`). No adopter file was modified.
- **Judgement rules.** Per rule and repo, findings were sampled at evenly spaced
  positions in the report's order: all when there were at most 8, otherwise 8
  (not 20: each label needs the code read). Each sampled finding was read in
  its source and labelled true or false positive with a reason. True means a
  maintainer reading the finding would agree the code has the named smell.
- **Mechanical rules** (`layer-import`, `unlayered-module`, `thick-entry`,
  `size-cap`) state a fact about the code, so every finding was rechecked by an
  independent script that does not call the tool: layer of source and target
  recomputed from the declared globs with `fnmatch` and the import found on the
  reported line; parameter, method and line counts and cyclomatic complexity
  recounted with `ast`. All findings were checked, not a sample.
- **`domain-io`** states a claim ("domain module depends on IO"), so all 47
  findings were read: a `pathlib` or `json` import that is only used for
  annotations or in-memory (de)serialisation is false.
- Labels reflect one reader's judgement, made from the code at each finding. The
  data-placement rules (`envied-data`, `feature-envy`, `data-clump`) were
  labelled from the finding, its class or function and the nature of the type
  (a dependency or parameter bundle is false; a record whose fields are computed
  on elsewhere is true); consumers were not traced.

## Result

| Rule | vox | quarry | lux | z-spec | All (true/sampled) | Precision |
|------|-----|--------|-----|--------|--------------------|-----------|
| `layer-import` | 168/168 | 306/306 | 106/106 | 28/28 | 608/608 (all) | 100% |
| `unlayered-module` | 149/149 | 7/7 | 12/12 | 0/0 | 168/168 (all) | 100% |
| `thick-entry` | 23/23 | 24/24 | 11/11 | 0/0 | 58/58 (all) | 100% |
| `size-cap` | 28/28 | 16/16 | 36/36 | 2/2 | 82/82 (all) | 100% |
| `stateless-single-method` | 7/8 | 8/8 | 8/8 | 0/0 | 23/24 | 96% |
| `misplaced-function` | 1/1 | 0/0 | 0/0 | 1/1 | 2/2 | 100% (2 findings: too few) |
| `stateless-function-bag` | 8/8 | 7/8 | 1/8 | 0/0 | 16/24 | 67% |
| `concrete-cross-package-import` | 4/8 | 5/8 | 7/8 | 4/6 | 20/30 | 67% |
| `data-clump` | 4/7 | 1/7 | 7/7 | 0/0 | 12/21 | 57% |
| `middle-man` | 1/3 | 1/1 | 0/0 | 0/0 | 2/4 | 50% |
| `tag-switch` | 2/2 | 1/6 | 0/0 | 1/1 | 4/9 | 44% |
| `feature-envy` | 5/7 | 2/7 | 1/7 | 1/1 | 9/22 | 41% |
| `envied-data` | 2/6 | 3/6 | 2/6 | 1/3 | 8/21 | 38% |
| `domain-io` | 5/22 | 10/20 | 1/2 | 1/3 | 17/47 (all) | 36% |
| `getter-heavy` | 2/4 | 0/2 | 2/8 | 0/0 | 4/14 | 29% |
| `split-cohesion` | 1/8 | 1/8 | 2/8 | 0/6 | 4/30 | 13% |
| `primitive-params` | 0/7 | 1/7 | 1/7 | 0/0 | 2/21 | 10% |

Cells are true/sampled. Finding counts per repository (vox, quarry, lux, z-spec):
`layer-import` 168/306/106/28, `unlayered-module` 149/7/12/0, `thick-entry`
23/24/11/0, `size-cap` 28/16/36/2, `stateless-single-method` 29/12/10/0,
`stateless-function-bag` 36/26/34/0, `concrete-cross-package-import`
41/124/63/6, `data-clump` 18/68/7/0, `middle-man` 3/1/0/0, `tag-switch`
2/6/0/1, `feature-envy` 30/33/11/1, `envied-data` 6/20/8/3, `domain-io`
22/20/2/3, `getter-heavy` 4/2/10/0, `split-cohesion` 65/48/61/6,
`primitive-params` 28/32/9/0, `misplaced-function` 1/0/0/1.

## What it decides

"Gate" means: `oo-ratchet design --shadow-check REF --enforce` exits 1 when the
comparison against the merge base adds a finding of a gate-capable rule. It is
off by default; without `--enforce` the shadow check exits 0 as before. The
gate-capable list is `Rules.GATE_CAPABLE` in `src/oo_ratchet/core/domain/findings.py`:

- `layer-import`, `unlayered-module`, `thick-entry`, `size-cap`: 100%, every
  finding verified.
- `stateless-single-method`: 96% on 24 of 51 findings. Its one false finding
  is class-level state read as no state (below).

`misplaced-function` is 2 of 2 but has two findings in four repositories: too few
to call it measured, so it stays advisory. Every other rule is under 70% and
stays advisory; `docs/DESIGN.md` states each number.

`domain-io` is 36% and is nevertheless in Tier 0 of the shadow verdict
(`would-fail: tier0`). Those tier labels are unchanged here; the 36% is the
measured reason to move it, and it is not gate-capable.

## False-positive causes seen

- **Class-level state counted as no state.** `stateless-single-method` and
  `stateless-function-bag` read a class whose only data is a mutable `ClassVar`
  (a lock and a weak set in lux `GuardRegistry`, a cached launchd manager in vox
  `AudioContext`, shared ledgers in quarry `FinalizeLedgers`) as stateless.
- **Classes with no instance fields.** `split-cohesion` fires on a class that has
  no instance fields (ports, gateways, codecs, registrars): 14 of 30 samples.
  LCOM4 is not defined without fields, and `stateless-function-bag` already
  reports those classes.
- **Value objects with accessors.** `getter-heavy` fires on frozen value objects
  (`WireAction`, `WindowHints`, `OutputFlags`, `GitFailure`): the encapsulation
  targets of this tool ask for private fields with read-only accessors.
- **Two primitive parameters.** `primitive-params` fires on `(cols, rows)`,
  `(session, baseline)` and similar pairs, 19 of 21.
- **Pure serialisation or annotation imports.** `domain-io` fires on `json`
  (no file access) and on `pathlib` used only in annotations.
- **Dependency bundles.** `envied-data` and `feature-envy` fire on classes whose
  job is to be read (`Ctx`, `*Deps`, `*Ports`, `*Options`) and on `__new__`
  methods that unpack one.
- **Enum-to-value mappings.** `tag-switch` fires on a `match` that maps each
  enum member to a string or another member (5 of 6 in quarry).
- **Command and port implementations.** `stateless-function-bag` fires on lux
  command objects (`execute` plus `__call__`, handed to a dispatcher), and
  `middle-man` on vox gateway adapters that implement a port.

## Raw labels

T is true, F is false. `repo#N` is the Nth finding of that rule in the report's
order.

### stateless-single-method

vox: #0 ProseCurrency T (classmethod namespace); #3 CallCli T; #7 MicCaptureCheck
T (called `MicCaptureCheck().run()`); #10 CallWorkerChecks T; #14 HookRedaction T;
#18 AudioContext F (class-level cache); #21 PlaylistMusic T; #25 WorkerBootstrap T.
quarry: #0 Backfill, #1 CaptureSnapshot, #3 StartupSweep, #4 StepReport, #6
RedirectLocation, #7 ProfanityInflector, #9 TranscriptRecords, #10 UrlSafetyCheck
all T. lux: #0 BeadsDetail, #1 CallbackMenu, #2 FieldGate, #3
HubInteractionDispatch, #5 CompositionBoundary, #6 DisplayModeOperations, #7
OperationFailure, #8 AppletRecords all T.

### stateless-function-bag

vox: #0 CodeCurrency, #4 InlineCode, #9 WorkerCli, #13 KeyAdmission, #18 LogText,
#22 SpokenAnswer, #27 WorkerDiscard, #31 TmuxProbe all T. quarry: #0
ReadAdmission T; #3 CaptureNaming T; #6 CheckRunner T; #9 FinalizeLedgers F
(shared per-database ledgers); #13 WebIngest T; #16 MissionMemoryComposer T; #19
RedactedFailure T; #22 SessionStartTemplates T. lux: #0 BeadsPayloadBuilder T; #4
DisplayInfoCommand F, #8 DisplayWindowGetCommand F, #12 MenuLsCommand F, #17
SceneDashboardCommand F, #21 SceneTableCommand F, #25 TopicPublishCommand F (each:
`execute` plus `__call__`, a module-level singleton the dispatcher calls); #29
GuardRegistry F (`ClassVar` WeakSet and Lock).

### getter-heavy

vox: #0 LifecycleSystem T (parameter holder); #1 ProgramSubsystem T; #2
AgentSettings F; #3 GitFailure F (value objects). quarry: #0 Database F (facade
over its parts); #1 _CorpusTally F. lux: #0 BdOutput F; #1 OutputFlags F; #2
WireAction F; #3 RenderLoop T; #5 WindowHints F; #6 RenderState F; #7
HubStoreFactory T; #8 NamedSession F.

### middle-man

vox: #0 ClientRecordGateway F and #1 ClientProgramGateway F (adapters of a port);
#2 VoxMarker T. quarry: #0 EnabledMarker T.

### misplaced-function

vox voice_not_found_message T (reads `exc.available` and `voice_name`); z-spec
render_schema_box T (reads six fields of `ZBlock`).

### tag-switch

vox: #0 SessionContext.ingest T; #1 StateInvariants._verify_mode_shape T. quarry:
#0 TranscriptStore._captured T; #1 AbortRecord._term_of F, #2 GpuStatus.outcome F,
#3 GpuStatus.symbol F, #5 StopTimeoutVerdict.message F (enum to value tables); #4
_Glob._token F (character scanner). z-spec: parse_spec T (block-kind chain).

### envied-data

vox: #0 Ctx F; #1 DedupHit T; #2 MeasuredFile F; #3 WorkerProgress T; #4
WorkerLaunch F; #5 WorkerInput F. quarry: #0 BackfillRuntime F; #3 FlushBatch T;
#6 CheckEntry F; #10 LoadedTranscript T; #13 CheckResult F; #16 SyncResult T. lux:
#0 FrameRemoveRequest F; #1 DrainedBatch T; #2 Settlement T; #4
OperationsConcerns F; #5 HubPorts F; #6 SceneOperationsDeps F. z-spec: #0
ProbOptions F; #1 AnimateOptions F; #2 ZBlock T.

### feature-envy

vox: #0 VoiceCommand._list T; #4 SegmentBatch._spec_for T; #8
TransientFailure._continue_retry T; #12 RecordHandler._store_outcome F; #17
SynthesizeHandler._synthesize_and_enqueue F; #21 WorkerCleanup.run T; #25
WorkerLifecycle.report T. quarry: #0 UnindexableTranscripts.record T; #4
DeltaSubmission.submit F; #9 RegistrationLifecycle.run_purge F; #14
HookAgent._trace_transcript_outcome F; #18 PageChunker._chunk F; #23
WebIngest.ingest_url F; #28 RowJudge._judge T. lux: #0 FrameRemoveCommand.execute
F; #1 BatchTransaction._attempt F; #3 SuspectBook.settle T; #4
Operations.__new__ F, #6 MenuOperations.__new__ F, #7 SceneOperations.__new__ F
(unpack a deps bundle); #9 StreamPublisher.attach F. z-spec: render_schema_box T.

### data-clump

vox: #0 WorkerCli.start T; #2 AudioRequest F; #5 ProgramSummary F; #7
AlbumListRow F (wire records that mirror one another); #10 WorkerActor.steer T;
#12 WorkerRegistry.start T; #15 WorkerSteering._deliver T. quarry: #0
CaptureIngestRequest F; #9 IngestRequest F; #19 SearchHit F; #29 ChunkLabels F (the
extracted group itself); #38 ingest_document T; #48 Chunk F; #58 SearchResult F.
lux: #0 HubDisplay, #1 SubtreeInstaller, #2 SubtreeRemover (the same four
collaborators), #3 CanonicalFrameOwner.for_store, #4 ClientDetailsPort.for_store,
#5 Operations.for_store, #6 FrameOwnerFacts.for_store (the same four parameters)
all T.

### primitive-params

vox: #0 CodeCurrency.spell, #4 CheckResult.of, #8 SpeechText.for_synthesis, #12
KeyAdmission.replaces, #16 MusicProvider.generate_track, #20 VibeNudge.advance,
#24 HookContextStore.inputs_since all F (two or three unrelated primitives).
quarry: #0 format_frontmatter F; #4 TaskOutcome.unreachable F; #9
SessionContextBlock.render F; #13 FetchRefusedError.policy F; #18
ReadCaptureFilter.should_capture T (file_path, cwd, content_bytes); #22
scrub_and_log F; #27 Shown.either F. lux: #0 DisplayLinkage.classify F; #1
FrameExpiry.arm F; #2 ReadyHandshake.receive F; #3 ProcessPort.resize F (cols,
rows); #5 ViewerFlow.prepare F; #6 ViewerBindings.add T (peer, session, cols,
rows); #7 ViewerBindings.close_session F.

### concrete-cross-package-import

vox: #0 VoxClientSync T; #5 OutputFormatter F; #10 LiveScene F (data); #15
ProviderCredentials F (value); #20 HubOutageLog T; #25 AtomicFile F (utility); #30
ElevenLabsProvider T; #35 ConfigStore T. quarry: #0 ClientConfig F; #15 Settings
F; #31 Progress F; #46 RecallTelemetry T; #62 ShadowRepo T; #77 FileDiscovery T;
#93 SyncRegistry T; #108 Database T. lux: #0 LeafCertificate F; #7
SnapshotTransfer, #15 ClientLifecycle, #23 ClientSession, #31 HubDisplay, #39 Hub,
#47 HubMenuRegistry, #55 HubDisplay all T. z-spec: #0 AtomicFile T, #1
ClaudeMdImport T, #2 SettingsRules F, #3 RepoEnablement T, #4 LuxDisplay T, #5
CommandResult F.

### split-cohesion

vox: #0 CatalogGateway F (no fields); #8 ElevenLabsProvider F; #16 SessionConfig F
(one stray method); #24 LifecycleReport F (value object); #32 FetchDigest F; #40
OutputHealth T (probe and budget are separate); #48 ProgramStore F (no fields);
#56 CallHandlers F. quarry: #0 HttpxTransport F; #6 FsEventSource F, #12 Claim F
(no fields); #18 ThreadStep F; #24 TableChanges F; #30 PlainFlushTarget F, #36
FollowSymlinks F (no fields); #42 CollectionIngestor T (flush target and runner in
one class). lux: #0 BeadsPayloadBuilder F; #7 CrossHostPump F (no fields); #15
ImGuiDialogRenderer F; #22 TableRowPainter F; #30 Input T (keyboard and mouse
halves); #38 DialSocket T (frames and dial halves); #45 HubOwnershipError F
(exception); #53 SessionDispatch F. z-spec: AtomicFile, EnablementGate,
ZSpecMenuEntry, HubListener (no fields), ZSpecSubscription, ServerContext all F.

### domain-io (all 47)

vox, true: `_audio` pathlib (`.exists`), `types_cli_options` typer,
`voxd/synthesis_result` shutil, tempfile and pathlib (file open and unlink).
vox, false: `bare_name`, `hook_envelope`, `hook_payload`, `keys_env_merge`,
`keys_env_report`, `types`, `types_audio`, `types_cli_options` (pathlib),
`voxd/playback_result`, `voxd/programs/producer` (pathlib, annotations only);
`music_faults`, `music_hint`, `settings_document`, `types_programs/mpv_event`,
`types_programs/wire`, `voxd/hook_context_projection` (json, in-memory only);
`types_programs/identifiers` (os, no IO call).
quarry, true: `collection_routing`, `collections`, `lesson`,
`read_capture`, `registration_rules` (pathlib `.resolve`), `post_sync_gc`
(`.open`), `scratch_paths` (`.exists`), `unindexable_entries` (`.stat`),
`sync_change` (`os.stat`), `url_safety` (socket DNS lookup). False:
`extractors/protocol`, `ignore_spec` (pathlib annotations); `read_capture`,
`shadow/visibility`, `transcript_records`, `web_capture`, `web_search_capture`
(json in memory); `transcript_records` (io), `failure_reason` (sqlite3 error
types), `scrub` (socket, no IO call).
lux, true: `hub/ready_handshake` socket. False: `pty/viewer_flow` json.
z-spec, true: `parser` pathlib (`.read_text`). False: `types/enablement`,
`types/tutorial` (pathlib annotations).

### Mechanical rules

`layer-import`: for each finding the source layer, the target layer and the
direction (target further out) were recomputed from the repository's declared
globs, and the target name was found on the reported line: 608 of 608. A false
finding would be a declared table that disagrees with the code; the tool and the
table agreed in every case. `unlayered-module`: 168 of 168 matched no glob.
`thick-entry`: 58 of 58 recounted complexity equal to the reported value.
`size-cap`: 82 of 82 recounted (80 by `ast` for parameters, methods and code
lines; the 2 complexity findings, both quarry, by the same recount as
`thick-entry`).

## Cheap false positives that became eval cases

- **`split-cohesion` on a class with no fields and no calls between its
  methods.** `evals/design/decoys/*/loans/adapters/gateway.py` (a port
  implementation, three methods, no fields) failed the precision test with
  `('split-cohesion', 'adapters/gateway.py', 'Gateway')` on the unfixed code;
  `MethodGraph.components` now returns 1 when no method touches a field or calls
  another method. On the four repositories the rule's findings fall from 65, 48,
  61, 6 to 45, 36, 50, 5 (vox, quarry, lux, z-spec). The precision above is for
  the rule before this change; it was not re-measured.
- **Not changed: class-level mutable state** in the two stateless rules (three
  false findings). Telling a mutated `ClassVar` from a constant table needs a
  mutation analysis, not a one-line exemption, so it is left as a finding for
  the next unit.
