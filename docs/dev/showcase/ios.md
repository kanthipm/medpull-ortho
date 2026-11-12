# The demo iPhone app (MedPull Demo)

The showcase's phone: an iPhone app with no accounts. It asks the demo
server who its fictional people are, signs in as whichever one the presenter
picks (Clinic, Personal or Sports), shows that person the screens the real
app would, and opens the links the demo's texts carry at the right screen.
For a clinic person it adds what the real iPhone app does not have yet: the
exercise calendar and the guided session, natively.

The contract it is built to is `docs/dev/showcase.md` ("The demo API",
"Links", "The demo iPhone app"). This page is what was actually built.

## The target

`ios/project.yml` (XcodeGen) has a second application target beside
`MedPull`:

| | MedPull (the App Store app) | MedPullDemo |
| --- | --- | --- |
| Bundle id | `com.medpull.recovery` | `com.medpull.demo` |
| Display name | MedPull | MedPull Demo |
| URL scheme | `medpull` | `medpulldemo` |
| Built against (`MEDPULL_API_BASE_URL`) | the production stack | `https://demo.medpull.app` |
| Entitlements | HealthKit | Associated Domains (`applinks:demo.medpull.app`) |
| Links | VitalCore, VitalHealthKit, StoreKit | none of them |
| Icon | `AppIcon` | `AppIconDemo` (the same mark with a DEMO band) |
| Compilation conditions | `DEBUG` | `DEBUG DEMO_APP` (Release: `DEMO_APP`) |

Team `2DFDVFGSH3`, iPhone only, iOS 17, portrait, like the real app. A
third target, `MedPullDemoTests`, holds the demo's unit tests. The scheme
`MedPull` is unchanged; the scheme `MedPullDemo` builds the demo app and runs
those tests.

    ios/MedPullDemo/
      MedPullDemoApp.swift      the entry: AppModel, DemoShell, ExerciseStore, Appearance
      Shell/                    DemoShell (personas, sign-in, links, the server), DemoAPI
                                (wire types and calls), DemoRootView (the tabs), DemoLink,
                                Keychain and StandIns (see "What is shared")
      Picker/                   "Who do you want to be?": versions, then people
      Profile/                  the presenter's sheet, Text my phone, the server address,
                                the simulated-devices screens
      Exercises/                the calendar, the exercise screen, the guided session
      Demo.xcassets             AppIconDemo
      Resources/                sample-attempt.mp4 (see "Stand-ins")
      Tools/                    make-icon.swift, make-sample-clip.swift (not in the app)
      Tests/                    the unit tests (their own target)
      Info.plist, MedPullDemo.entitlements    written by XcodeGen from the spec

`Info.plist` and the entitlements file are regenerated from `project.yml` on
every `xcodegen generate`, as the real app's are: the spec is the source of
truth.

## What is shared with the real app, and why

The demo target compiles the real app's own files, not copies: the design
system (`ios/MedPull/UI`, the fonts, `Assets.xcassets`), all of
`ios/MedPull/Core` except three files, and the feature screens a signed-in
person sees (Care, Checkin, Tasks, Today, Progress, Measure; from Personal
`PersonalHomeView`, `StatsView`, `MetricsView`, `PanelViews`; from Sports the
home, Stats, Recovery, Injury, the motion tests, the sheets and the shared
components). A change to a shared screen reaches both apps, and one that
breaks the demo fails in the same `xcodegen generate` and build.

It leaves out what needs an account or an entitlement: onboarding, the real
Profile and its Connections screens, the paywall, consent, spaces, and three
Core files:

| Left out | The demo's own, with the same name | Why |
| --- | --- | --- |
| `Core/HealthConnector.swift` | `Shell/StandIns.swift` | Apple Health through the Vital SDK: nothing on this phone to connect, and no HealthKit entitlement |
| `Core/Store.swift` | `Shell/StandIns.swift` | StoreKit: no demo person is asked to pay |
| `Core/Keychain.swift` | `Shell/Keychain.swift` | the same four calls, kept in the keychain and in UserDefaults (see "The session") |
| `Features/Profile/ProfileView.swift` | `Profile/ProfileView.swift` | the avatar at the top right of Today opens the presenter's sheet |
| `Features/Profile/ConnectionsView.swift`, `Features/Sports/SportsDevicesView.swift` | `Profile/SimulatedDevices.swift` | they say the person's devices are simulated and list, read-only, what the server reports as connected |

Seven edits were made under `ios/MedPull/` so both targets can compile the
same files. Each is inert for the real app:

- `UI/BrandFlow.swift`: `BrandFlow` moved out of
  `Features/Onboarding/OnboardingFlow.swift` unchanged (a shared Sports
  component uses it; onboarding is not in the demo).
- `Features/Profile/ProfileFormatting.swift`: `ProfileView.versionLine` and
  `ProfileView.displayDate` moved out of the real `ProfileView.swift` into an
  extension, unchanged, so each target's own `ProfileView` gets them (a shared
  Sports screen calls `ProfileView.displayDate`).
- `Core/AppModel.swift`: `Tab` has one more case, `calendar`, inside
  `#if DEMO_APP`.
- `Core/MotionCapture.swift`: `import HealthKit` and the body of
  `healthHeightCm()` are inside `#if !DEMO_APP`; the demo returns nil, and
  the Measure screen asks for the height, as it already does when Health has
  none.
- `Features/Today/TodayView.swift`: two `#if DEMO_APP` blocks, the exercise
  card under the greeting, above the hero (`TodayExercises()`), and the modifier
  that reads the day and pushes the exercise screen (`.todayExercisesHost()`).
- `Core/Models.swift`: `MessageAction` has one more property, `target`,
  inside `#if DEMO_APP`: where a texted line's link opens, as the server sends
  it (`action.target`, the shape a redeemed link answers with).
- `Features/Care/Conversation.swift`: one `#if DEMO_APP` block in the bubble.
  A line a text carried with a link gets a button with the link's label
  (`ThreadPlaceButton`, in `ios/MedPullDemo/Shell`), which calls
  `DemoShell.go(to:)`, the navigator a tapped link uses. The real app has no
  such navigator and draws these lines as words, as before.

`DEMO_APP` is defined only in the `MedPullDemo` target's build settings, so
for `MedPull` every one of those blocks compiles to nothing. `make ios-build`
is the check.

## The decision about `AppModel`

The demo compiles the real `Core/AppModel.swift` rather than a class of its
own with the same members.

Every shared screen reads `AppModel` from the environment and calls its
feeds and actions. A second class would have to copy five hundred lines and
then be kept in step by hand; the first
shared screen to use a member the copy lacked would break the demo, and a
copy that drifted quietly (the banner rule, the 401 handling, the order of
the first reads) would make the demo behave unlike the app it is showing.
Sharing the class costs three small stand-ins for the types it owns
(`HealthConnector`, `Store`, `Keychain`), which do nothing, and one guarded
line (the `calendar` tab).

What the real class has no notion of sits beside it, not in it: `DemoShell`
(who can be picked, becoming one of them, the links, the server) and
`ExerciseStore` (the exercise calendar). The shared screens never read
either; the demo's own screens do. `AppModel.phase` means what it means in
the real app, except that "onboarding" here is the picker.

Two consequences worth knowing. `AppModel.bootstrap()` runs unchanged, so
`-MP_SESSION_TOKEN`, `-MP_TAB` and `-MP_HOLD_LAUNCH` work as in the real app.
And a Personal persona's open calls `startDay`, as the real app's does, which
is a write: it is what lets the server text that person's brief to a phone
bound with "Text my phone".

## The session

`POST /api/demo/session` and `POST /api/links/{token}/session` both answer a
`session_token` and `me`; `DemoShell.adopt` hands them to
`AppModel.adoptSession`. The token is kept under the same key the real app
uses, by the demo's `Keychain`: in the keychain when there is one, and in
UserDefaults as well (`demo_session.*`). The real app must not put a
patient's token in UserDefaults; the demo's tokens belong to fictional
people, and an unsigned simulator build has no keychain at all, so without
the second copy the chosen person would be forgotten at every launch there.

The demo's front door (the persona list, the session, the day reset, the
links, `/api/health`) is called on a client that never carries a token, so
those requests go out with no `Authorization` header. `/api/demo/phone` and
everything under `/api/mobile` go out on the signed-in client.

Becoming someone else empties the feeds first (`ExerciseStore.reset`, then
the lists on `AppModel`), and the tabs are keyed by the person's id, so
nothing one person opened or typed is on screen for the next. A 401 on any
read signs out, as in the real app, and lands on the picker.

The token a sign-in or a link returns is always taken, even when it is for
the person already signed in. The demo session route keeps one live session
per person and device, so the token just issued is the one certain to work;
for a link either token would do today, and taking the new one stays right
if the link route ever replaces the device's earlier session too.

## The shell

- **Who do you want to be?** `Picker/PersonaPicker.swift`. The three
  versions as cards with the count of people in each, then the people in one
  version grouped by organisation, the hero first with their tagline, the
  day's story and the tier as a chip. Loading, empty and failed states are
  drawn; a failed list offers a retry and the server address. A bare 404
  reads "This server has no demo people on it", which is what any server
  without the demo routes answers.
- **Tabs.** `Shell/DemoRootView.swift`, composed as the real `RootView`
  composes them. Clinic: Today, Calendar, Progress, Measure, Care. Personal:
  Today, Trends, Coach. Sports: Today, Stats, Recovery, Injury, Coach. No
  paywall cover and no consent gate.
- **The switcher.** The demo's `ProfileView`: who the app is being, Switch
  person, Switch version, Text my phone, Reset today (clinic people;
  `POST /api/demo/reset-day`), the simulated devices, appearance, the server
  address and whether that server is a demo (`GET /api/health`: `demo`, and
  `showcase.filled_on` when it is sent), the version line, Start over.
- **Links.** `medpulldemo://a/<token>` and `https://<host>/a/<token>`
  (`onOpenURL` and the browsing-web user activity) both become
  `DemoLink.token`. `DemoShell.redeem` reads the link, exchanges it for a
  session, becomes that person and opens the target: `today`, `exercise`
  (the exercise screen for `ref_id`), `program` (Calendar, on `day` when the
  link names one), `task` and `checkin` (the task for `ref_id`), `thread`
  (Care), `measure`, `progress`. Where the link lands is held in
  `ExerciseStore` (`openOnToday`, `calendarDay`) and `AppModel`
  (`pendingTaskId`, `selectedTab`), not in the screens, because a link that
  changes who the app is rebuilds every screen. A link that fails shows a
  small sheet with the server's sentence. One that arrives before launch has
  finished is held until it has. `medpulldemo://tasks/<id>`, `medpulldemo://exercises/<id>`
  and the older `/t/<token>` task link are answered too.
- **Text my phone.** `Profile/TextMyPhoneSheet.swift`, on
  `GET | POST | DELETE /api/demo/phone`. While the answer says
  `reachable: false` the sheet shows "Text us first" (the line's number, the
  words already written, a button that opens Messages through an `sms:` URL)
  and asks again every three seconds; when it turns true, "You're
  connected". A 409 shows the server's sentence (or, when it sends none,
  that the number belongs to someone else); a 404 says texting is not
  available on this server.

## The exercise calendar and the guided session

The patient web app's exercise screens
(`patient-web/src/features/exercises`), ported to SwiftUI in the app's own
vocabulary. Everything is under `ios/MedPullDemo/Exercises/`.

| File | What |
| --- | --- |
| `ExerciseModels.swift` | the wire types, decoded by hand so a field a newer server adds (or drops) does not sink a row; loads in the clinic's unit; the words |
| `ExerciseAPI.swift` | the calls: the day, the program, start, complete, skip, the staged upload, a clip's bytes, `/api/health` |
| `ExerciseStore.swift` | the two feeds, the watch that keeps them fresh, the three actions |
| `TodayExercises.swift` | the card on Today, and the host modifier Today carries |
| `CalendarTab.swift` | the Calendar tab |
| `ExerciseScreen.swift`, `ExerciseSheets.swift` | one exercise; "Just mark it done" and "Can't do it today" |
| `GuidedSession.swift` | the session, a stage at a time |
| `ExerciseClips.swift`, `ExerciseAttempt.swift`, `ExerciseComponents.swift` | the clip tile and its files; the clip of the attempt; rows, the two sliders, the "what you did" fields, the outcome card |

- **Feeds.** `GET /api/mobile/exercises?date=` with the phone's own day, and
  `GET /api/mobile/exercises/program?start=&days=14` from a week back. While
  Today, the Calendar or an exercise is on screen the store reads again every
  ten seconds and at once when the app returns to the foreground, so an
  exercise assigned on the console appears without a pull. Watching screens
  are counted, so two of them (the session over the exercise it was started
  from) share one loop.
- **State.** The server stores three (`assigned`, `done`, `skipped`). To
  do, in progress (started today, not finished), missed (open and the day has
  passed) and planned are read off the day and the session by the console's
  own rule (`state_of` in `backend/app/hep/schedule.py`, which the calendar
  stream added), so the app does not depend on the `state` field that stream
  put on a row.
- **Loads.** Kilograms are what a row stores and what the app sends. When
  the feed's `clinic.load_unit` is `lb` the app shows and takes pounds, with
  the server's factor and rounding (pounds to a tenth, kilograms to two
  decimals), so 25 lb typed comes back as 25 lb. The dose line is the
  server's own string.
- **Clips.** A demonstration's link lasts minutes (a presigned URL) or
  needs the session (a path into the API on a server with no object store),
  so no link is kept or handed to a player: the bytes are fetched once, from
  the link in the feed as it is then (read again if it had expired), and the
  player loops a file. Muted, mixed with whatever the person is listening to.
- **The clip sent back.** A recording from the camera or a video from the
  library goes through the shared `AttachmentPrep.video`, as a clip on the
  Care thread does (540p H.264 in an MP4). The upload follows the ticket
  (`GET /api/mobile/attachments/upload-ticket`): a presigned multipart POST
  straight to object storage, with none of the app's own credentials on it,
  or, on a server with no object store, the bytes to the API's direct
  route, which confirms the file as it stores it. A presigned upload is
  left unconfirmed (the thread's uploader confirms at once; this one does
  not): the completion carries the clip (`video`: the storage key, or the
  direct route's attachment id) and the server confirms the key there,
  beside the day it belongs to.
- **The session's stages.** Start (the pain right now; `POST …/start`) →
  your watch, unless the therapist turned it off → set up your phone → do it
  (her clip looping, the sets counted, a sixty-second rest that can be
  skipped, a countdown when a set is one timed hold, the clock from Start) →
  record, unless she turned that off (the system camera through the shared
  `CameraCapture`, or a video from the library) → the clip uploading → the
  pain now, the effort, what was actually done (sets, reps and load, filled
  in from the dose and the session's own count, and the person's to change)
  and a note (`POST …/complete`) → done. The stages are fixed when the
  session opens. It covers the tab bar, leaving asks first, the screen stays
  awake, and the phone taps at every change.
- **Refusals.** A 422 or 409 is shown as the server's own sentence at the
  step that sent it: Start, or the answers. "Just mark it done" keeps Send
  off, and says why, while a clip or the watch she required is missing.
- **Settled from somewhere else.** When the watch finds the row done or
  skipped while its session is open (the therapist logged it from the room,
  or it was sent from another device), the session stops where it is, shows
  what was recorded and offers the way back to the exercise. A skipped row
  has no Start on the exercise screen, as in the patient web app, although
  the server would put it back to `assigned` on `/start`.
- **The done screen** shows the row as the server answered it, the
  session's length included, so the line under the seal (a clock, "1:35")
  and the card (in words, "2 min") are the same figure, written the two
  ways the web app writes them.

## Stand-ins, and how each is labelled

Nothing in the app analyses a movement or reads a watch, and nothing says it
does.

- **The watch stage.** No demo person's watch is paired with the phone. The
  stage waits two seconds and shows "Detected", with "Simulated for this
  demo" under it. The person can always say "I'm not wearing a watch": an
  exercise that requires it then waits, one that does not carries on.
- **The sample clip.** Offered only when `/api/health` says the server is a
  demo. It sends the therapist's own demonstration when the exercise has
  one, else `Resources/sample-attempt.mp4` (a drawn figure with "Sample
  clip · not a person's recording" on every frame;
  `Tools/make-sample-clip.swift` redraws it). It is called a sample on the
  button, under the preview and on the upload stage, and reaches the server
  as `sample-attempt.mp4`.
- **The upload stage** is an upload and is named one: a real `POST` with
  its real progress.
- **The devices screens** say the person's devices are simulated and list
  what the server reports.

## Launch arguments

Debug builds only, except `-api_base_url` and `-appearance_mode`, which are
ordinary stored settings given as arguments.

| Argument | Does |
| --- | --- |
| `-api_base_url <url>` | the server for this launch |
| `-appearance_mode light\|dark\|system` | the appearance for this launch |
| `-MP_DEMO_PERSONA <id>` | signs in through `POST /api/demo/session` at launch |
| `-MP_SESSION_TOKEN <token>` | the real app's path: signs in with a minted token |
| `-MP_TAB calendar\|progress\|measure\|care\|recovery\|rehab\|connections` | the tab to open on (`connections`: the devices screen over Today) |
| `-MP_OPEN_LINK <token or whole link>` | opens it as a tap in Messages would |
| `-MP_DEMO_VERSION clinic\|personal\|sports`, `-MP_SHOW people` | the picker, on that version's people |
| `-MP_PICK <persona id>`, `-MP_PICK_AFTER <seconds>` | on a people screen: chooses that person, through the call a tap makes, after that long (two seconds when not said) |
| `-MP_HOLD_ROSTER <seconds>` | holds the picker's loading state |
| `-MP_SHOW profile`, `-MP_PROFILE people\|versions\|phone\|devices\|server\|reset\|resetnow\|startover`, `-MP_SCROLL_PROFILE demo\|server` | the profile sheet, what to open or do in it, and where to scroll it |
| `-MP_PHONE <number>` | in Text my phone: types the number and presses "Use this number" |
| `-MP_EXERCISE <assignment id>\|first\|required\|hold\|done\|reviewed\|skipped` | opens that exercise |
| `-MP_EX_SHOW session\|mark\|skip` | on the exercise: the session, or one of the two sheets |
| `-MP_EX_STAGE <stage>[:<state>]` | opens the session at `start`, `watch[:looking\|none]`, `setup[:leave]`, `exercise[:rest\|hold\|all\|last]`, `record[:taken]`, `upload[:hold\|failed]`, `finish` |
| `-MP_EX_AUTO <seconds>` | every stage takes its own primary action after that long: one launch walks the session through the real calls, with the sample clip |
| `-MP_EX_FILL 1`, `-MP_EX_SEND 1`, `-MP_EX_SKIP <reason>` | answer the completion sheet; press Send; pick a skip reason |
| `-MP_EX_SCROLL middle\|bottom`, `-MP_CAL_DAY <yyyy-MM-dd, or days ahead of today>` | what a screenshot shows (a day behind today needs its date: `-2` would be read as the next argument's name) |

The shared screens' own arguments (`-MP_SCROLL`, `-MP_OPEN`, …) work as in
the real app.

## Running it on the simulator against a local server

The app is built against the public demo, so every local launch names the
local server. Never launch it bare on a machine that should not call out. A
launch argument is easy to lose (a shell that does not split a variable
hands the app one argument that names no server), so where that matters
build the app with the address overridden, and its built-in server is the
local one whatever the launch says:

    cd ios && xcodegen generate && xcodebuild -project MedPull.xcodeproj -scheme MedPullDemo \
      -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_ALLOWED=NO \
      MEDPULL_API_BASE_URL=http://localhost:8108 build

Otherwise:

    # the API, from backend/ (DEMO_MODE turns the demo routes on)
    DEMO_MODE=true DATABASE_URL=sqlite:///<scratch>/dev.db ATTACHMENT_DIR=<scratch>/attachments \
      GROQ_API_KEY= SENDBLUE_API_KEY= SENDBLUE_API_SECRET= S3_BUCKET= WARM_CACHES_ON_STARTUP=false \
      uv run python -m app.seed.seed --reset
    (same environment) uv run uvicorn app.main:app --port 8108

    # the app
    make ios-demo-build          # xcodegen + an unsigned simulator build
    xcrun simctl boot "iPhone 17"
    xcrun simctl install booted <DerivedData>/Build/Products/Debug-iphonesimulator/MedPullDemo.app
    xcrun simctl launch booted com.medpull.demo -api_base_url http://localhost:8108 \
      -MP_DEMO_PERSONA hirt-cole
    xcrun simctl io booted screenshot shot.png

`xcrun simctl openurl booted medpulldemo://a/<token>` works once the app is
running, but iOS asks "Open in MedPull Demo?" first, which nothing on the
command line can answer: use `-MP_OPEN_LINK`. Universal links need a signed
build (an unsigned one carries no entitlements).

## Tests

`make ios-demo-test` (`xcodebuild test -scheme MedPullDemo`, unsigned, on
the simulator). `Tests/DemoContractTests.swift` decodes the JSON examples in
`docs/dev/showcase.md` with the app's types, a sloppier version of each, the
link parser and the phone-number helpers. `Tests/ExerciseModelTests.swift`
decodes rows a local server answered (with the fields the calendar stream
added), and checks the states, the loads in both units, the completion body
and the session's stages. While tests run the app shows nothing and calls
no server.

## A real phone: what the owner does on Apple's side

1. **Register the App ID.** In Certificates, Identifiers & Profiles, add
   `com.medpull.demo` under team `2DFDVFGSH3` with the **Associated
   Domains** capability. (Xcode's automatic signing will register the id on
   the first signed build, but the capability has to be on it for the
   entitlement to be granted.)
2. **Sign.** Open `ios/MedPull.xcodeproj` (`make ios`), pick the
   `MedPullDemo` scheme and a phone, and let automatic signing make the
   profile. `MedPullDemo.entitlements` asks only for
   `applinks:demo.medpull.app`.
3. **Publish the association file from the demo stack.** The server's
   `/.well-known/apple-app-site-association` must name
   `2DFDVFGSH3.com.medpull.demo` for `/a/*` and `/t/*`: set
   `IOS_LINK_APP_IDS=2DFDVFGSH3.com.medpull.demo` on the demo stack
   (`ios_link_app_ids`; `IOS_BUNDLE_ID` stays the real app's, because it also
   gates App Store receipts). iOS fetches that file when the app is
   installed, through Apple's CDN, so a change can take a day to be seen.
   The custom scheme (`medpulldemo://a/<token>`, which the browser page for
   a link offers as "Open in the app") works without any of this.
4. **TestFlight.** A new app record in App Store Connect for
   `com.medpull.demo` ("MedPull Demo"). Bump `CURRENT_PROJECT_VERSION` in
   the `MedPullDemo` target (date, then `.1`, `.2`, as the real app's),
   archive the `MedPullDemo` scheme, upload. Internal testers need no
   review. Two things a review for external testers would ask about: the
   app signs in with no account (say that every person in it is fictional
   and the data is generated), and `NSAllowsArbitraryLoads` is on so a
   presenter can point it at a laptop over plain http.
5. **The icon.** `swift ios/MedPullDemo/Tools/make-icon.swift` redraws the
   three demo icons from the real app's, should those change.

## What is not there

- Heart rate during a session. The server reads it from watch samples
  inside the session's window; the demo reads no watch, so a completion sent
  from it carries `wearable_worn` and no heart rate unless the demo's fill
  wrote samples for that time.
- An exercise older than the fortnight on show. There is no single-exercise
  read on the server, so a link to one outside the day's feed and the
  program's fourteen days reads "That exercise isn't on your list".
- A text line of its own. Whether "Text my phone" reaches a phone is the
  demo stack's Sendblue configuration.
