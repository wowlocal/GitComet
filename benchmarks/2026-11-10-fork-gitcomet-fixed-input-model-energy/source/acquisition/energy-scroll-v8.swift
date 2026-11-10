// Separate v8 energy benchmark driver: validated session route; prior sources unchanged.
// Native AppKit foreground metadata only; no AX, event tap/listener or permission request.
// Generates scroll requests; CGEvent posting does not acknowledge app delivery.
import Foundation
import CoreGraphics
import AppKit
import Darwin

struct BenchFailure: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

struct ClockStamp: Codable {
    let monotonic_ns: Double
    let unix_s: Double
    let pair_bracket_ns: Double
}

struct PostedEvent: Codable {
    let kind = "posted_scroll_request"
    let run_id: String
    let index: Int
    let scheduled_monotonic_ns: Double
    let pixel_delta_y: Int32
    let creation_begin: ClockStamp
    let begin: ClockStamp
    let end: ClockStamp
    let start_lateness_ms: Double
    let target_pid_field: Int64
    let point_delta_y_field: Int64
    let continuous_field: Int64
}

var timebase = mach_timebase_info_data_t()
guard mach_timebase_info(&timebase) == KERN_SUCCESS, timebase.denom != 0 else {
    fputs("Unable to read monotonic timebase\n", stderr)
    exit(2)
}
let nsPerTick = Double(timebase.numer) / Double(timebase.denom)

func clockStamp() -> ClockStamp {
    let before = mach_absolute_time()
    let unix = Date().timeIntervalSince1970
    let after = mach_absolute_time()
    return ClockStamp(monotonic_ns: (Double(before) + Double(after)) * 0.5 * nsPerTick,
                      unix_s: unix, pair_bracket_ns: Double(after - before) * nsPerTick)
}

let encoder: JSONEncoder = {
    let value = JSONEncoder()
    value.outputFormatting = [.sortedKeys]
    return value
}()

func emit<T: Encodable>(_ value: T) throws {
    var data = try encoder.encode(value)
    data.append(0x0A)
    FileHandle.standardOutput.write(data)
}

struct Notice: Codable {
    let kind: String
    let run_id: String
    let stamp: ClockStamp
    let detail: String
}

func notice(_ kind: String, _ runID: String, _ detail: String) throws {
    try emit(Notice(kind: kind, run_id: runID, stamp: clockStamp(), detail: detail))
}

func waitUntil(_ deadline: UInt64) throws {
    while mach_absolute_time() < deadline {
        guard mach_wait_until(deadline) == KERN_SUCCESS else {
            throw BenchFailure("Absolute monotonic wait interrupted; attempt incomplete")
        }
    }
}

func ticks(after origin: UInt64, seconds: Double) -> UInt64 {
    origin + UInt64((seconds * 1e9 / nsPerTick).rounded())
}

func processCPUNanoseconds() throws -> UInt64 {
    var value = timespec()
    guard clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) == 0,
          value.tv_sec >= 0, value.tv_nsec >= 0, value.tv_nsec < 1_000_000_000 else {
        throw BenchFailure("Public process CPU clock unavailable; no guessed observer value")
    }
    return UInt64(value.tv_sec) * 1_000_000_000 + UInt64(value.tv_nsec)
}

struct DriverAccounting: Codable {
    let kind = "driver_accounting"
    let run_id: String
    let cpu_start_ns: UInt64
    let cpu_end_ns: UInt64
    let cpu_ns: UInt64
    let observer_start: ClockStamp
    let observer_end: ClockStamp
    let scope = "Own process CPU before timed origin through final guards/cursor restore; excludes buffered event serialization; not app CPU or energy"
}

func usage() {
    print("""
    energy-scroll-v8 --check-access
    energy-scroll-v8 --describe-target --pid PID --window-x X --window-y Y --window-width W --window-height H --x GLOBAL_X --y GLOBAL_Y
    energy-scroll-v8 --run-id ID --pid PID --window-id ID --window-x X --window-y Y --window-width W --window-height H --x GLOBAL_X --y GLOBAL_Y --pixels N [--initialize | --characterize]

    --describe-target reads public foreground/window metadata only, with no warp/posts/access request.
    Main:20s still,90s requests,20s still. Characterize:one10s polarity cycle. Initialize:240negative requests over2s.
    All requests120Hz,10s polarity cycle, required pixel magnitude1..64; initialize always negative.
    Public session insertion plus one cursor warp; foreground/pointer checked each request, full owned-window contract before/after.
    Pointer restored only if unchanged at frozen point. No AX/HID taps/listeners/clicks/keys/permission requests.
    Posting/readback is not delivered-event acknowledgement. Per-request native checks consume observer CPU.
    """)
}

struct FrozenWindow: Codable {
    let id: UInt32
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct TargetDescription: Codable {
    let kind = "target_description"
    let schema = "native-scroll-target-description-v1"
    let stamp: ClockStamp
    let pid: Int32
    let frontmost_pid: Int32
    let window: FrozenWindow
    let x: Double
    let y: Double
    let no_warp_or_posts = true
}

func describeTarget(_ pid: Int32, _ x: Double, _ y: Double, _ width: Double, _ height: Double, _ point: CGPoint) throws -> FrozenWindow {
    try requireForeground(pid)
    guard let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
        throw BenchFailure("Cannot describe public target window")
    }
    let owned = windows.filter { row in
        (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid &&
        (row[kCGWindowLayer as String] as? NSNumber)?.intValue == 0
    }
    guard owned.count == 1, let row = owned.first,
          let id = (row[kCGWindowNumber as String] as? NSNumber)?.uint32Value, id > 0 else {
        throw BenchFailure("Target must own exactly one on-screen layer0 window")
    }
    let frozen = FrozenWindow(id: id, x: x, y: y, width: width, height: height)
    try requireWindow(pid, frozen, point)
    return frozen
}

func requireForeground(_ pid: Int32) throws {
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid else {
        throw BenchFailure("Frozen target lost foreground; stop session posting")
    }
}

func currentPointer() throws -> CGPoint {
    guard let event = CGEvent(source: nil) else { throw BenchFailure("Cannot read pointer; no fallback") }
    let point = event.location
    guard point.x.isFinite && point.y.isFinite else { throw BenchFailure("Invalid pointer state") }
    return point
}

func requireWindow(_ pid: Int32, _ frozen: FrozenWindow, _ point: CGPoint) throws {
    try requireForeground(pid)
    guard let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
        throw BenchFailure("Cannot read public window metadata")
    }
    let owned = windows.filter { row in
        (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid &&
        (row[kCGWindowLayer as String] as? NSNumber)?.intValue == 0
    }
    guard owned.count == 1, let row = owned.first,
          (row[kCGWindowNumber as String] as? NSNumber)?.uint32Value == frozen.id,
          (row[kCGWindowAlpha as String] as? NSNumber)?.doubleValue == 1,
          let bounds = row[kCGWindowBounds as String] as? [String: NSNumber],
          bounds["X"]?.doubleValue == frozen.x, bounds["Y"]?.doubleValue == frozen.y,
          bounds["Width"]?.doubleValue == frozen.width, bounds["Height"]?.doubleValue == frozen.height,
          CGRect(x: frozen.x, y: frozen.y, width: frozen.width, height: frozen.height).contains(point) else {
        throw BenchFailure("Frozen single owned opaque window/bounds/point mismatch")
    }
    // The history subrectangle is separately witnessed by caller; this checks
    // topmost layer0 content at the supplied point, not only an obscured owner.
    guard let atPoint = windows.first(where: { row in
        guard (row[kCGWindowLayer as String] as? NSNumber)?.intValue == 0,
              let bounds = row[kCGWindowBounds as String] as? [String: NSNumber],
              let x = bounds["X"]?.doubleValue, let y = bounds["Y"]?.doubleValue,
              let width = bounds["Width"]?.doubleValue, let height = bounds["Height"]?.doubleValue else { return false }
        return CGRect(x: x, y: y, width: width, height: height).contains(point)
    }), (atPoint[kCGWindowNumber as String] as? NSNumber)?.uint32Value == frozen.id else {
        throw BenchFailure("Frozen target is not frontmost layer0 window at history point")
    }
}

struct CursorRestoration: Codable {
    let kind = "cursor_restoration"
    let run_id: String
    let stamp: ClockStamp
    let attempted: Bool
    let result_code: Int32?
    let reason: String
}

let args = Array(CommandLine.arguments.dropFirst())
var posted: [PostedEvent] = []
var runID = "unset"

do {
    if args == ["--help"] || args == ["-h"] { usage(); exit(0) }
    if args == ["--check-access"] {
        let allowed = CGPreflightPostEventAccess()
        try notice("access_preflight", runID, allowed ? "allowed; no events posted" : "denied; no request made, no events posted")
        exit(allowed ? 0 : 3)
    }
    var values: [String: String] = [:]
    var characterize = false
    var initialize = false
    var describe = false
    var cursor = 0
    let known: Set<String> = ["--run-id", "--pid", "--window-id", "--window-x", "--window-y", "--window-width", "--window-height", "--x", "--y", "--pixels"]
    while cursor < args.count {
        let key = args[cursor]
        if key == "--characterize" {
            guard !characterize else { throw BenchFailure("Duplicate characterize flag") }
            characterize = true
            cursor += 1
            continue
        }
        if key == "--initialize" {
            guard !initialize else { throw BenchFailure("Duplicate initialize flag") }
            initialize = true
            cursor += 1
            continue
        }
        if key == "--describe-target" {
            guard !describe else { throw BenchFailure("Duplicate describe flag") }
            describe = true
            cursor += 1
            continue
        }
        guard known.contains(key), cursor + 1 < args.count, values[key] == nil else {
            throw BenchFailure("Unknown, incomplete or duplicate argument")
        }
        values[key] = args[cursor + 1]
        cursor += 2
    }
    guard let pidString = values["--pid"], let pid = Int32(pidString), pid > 1,
          let wxString = values["--window-x"], let wx = Double(wxString), wx.isFinite,
          let wyString = values["--window-y"], let wy = Double(wyString), wy.isFinite,
          let wwString = values["--window-width"], let ww = Double(wwString), ww.isFinite, ww > 0,
          let whString = values["--window-height"], let wh = Double(whString), wh.isFinite, wh > 0,
          let xString = values["--x"], let x = Double(xString), x.isFinite, abs(x) <= 32768,
          let yString = values["--y"], let y = Double(yString), y.isFinite, abs(y) <= 32768 else {
        throw BenchFailure("Require accessible target PID, exact finite window bounds and history point")
    }
    if describe {
        guard !initialize && !characterize && values["--run-id"] == nil && values["--pixels"] == nil && values["--window-id"] == nil else {
            throw BenchFailure("Describe mode accepts only PID/bounds/point; no input mode")
        }
        let window = try describeTarget(pid, wx, wy, ww, wh, CGPoint(x: x, y: y))
        try emit(TargetDescription(stamp: clockStamp(), pid: pid, frontmost_pid: pid, window: window, x: x, y: y))
        exit(0)
    }
    guard !(initialize && characterize),
          let id = values["--run-id"], !id.isEmpty, id.count <= 128,
          let windowString = values["--window-id"], let windowID = UInt32(windowString), windowID > 0,
          let pixelString = values["--pixels"], let pixels = Int32(pixelString), (1...64).contains(pixels) else {
        throw BenchFailure("Require run-id/window ID/pixels1..64 and mutually exclusive initialize/characterize flags")
    }
    runID = id
    guard CGPreflightPostEventAccess() else {
        throw BenchFailure("Event-post access absent; stopped without request or permission change")
    }
    guard kill(pid, 0) == 0 else {
        throw BenchFailure("Supplied target PID not accessible before benchmark")
    }
    // Binary/start identity and history rectangle are caller-owned witnesses.
    let point = CGPoint(x: x, y: y)
    let frozen = FrozenWindow(id: windowID, x: wx, y: wy, width: ww, height: wh)
    try requireWindow(pid, frozen, point)
    let originalPointer = try currentPointer()
    var restorationPending = true
    var restorationFailed = false
    func restorePointerIfUnchanged() {
        guard restorationPending else { return }
        restorationPending = false
        do {
            let current = try currentPointer()
            if current == point {
                let status = CGWarpMouseCursorPosition(originalPointer)
                restorationFailed = status != .success
                try? emit(CursorRestoration(run_id: runID, stamp: clockStamp(), attempted: true,
                    result_code: status.rawValue, reason: "Pointer still at probe point; guarded best-effort restoration"))
            } else {
                try? emit(CursorRestoration(run_id: runID, stamp: clockStamp(), attempted: false,
                    result_code: nil, reason: "Pointer changed; preserve user position"))
            }
        } catch {
            restorationFailed = true
            try? emit(CursorRestoration(run_id: runID, stamp: clockStamp(), attempted: false,
                result_code: nil, reason: "Pointer unavailable; no blind restoration"))
        }
    }
    defer { restorePointerIfUnchanged() }
    let warpStatus = CGWarpMouseCursorPosition(point)
    guard warpStatus == .success else { throw BenchFailure("Initial public pointer warp failed") }
    guard try currentPointer() == point else { throw BenchFailure("Warped pointer does not equal frozen history point") }
    try requireWindow(pid, frozen, point)
    let rate = 120
    let periodEvents = rate * 10
    let idleBefore = (initialize || characterize) ? 0.0 : 20.0
    let activeSeconds = initialize ? 2.0 : (characterize ? 10.0 : 90.0)
    let idleAfter = (initialize || characterize) ? 0.0 : 20.0
    let count = Int(activeSeconds) * rate
    posted.reserveCapacity(count)
    let observerStart = clockStamp()
    let cpuStart = try processCPUNanoseconds()
    let origin = mach_absolute_time()
    let activeStart = ticks(after: origin, seconds: idleBefore)
    let activeEnd = ticks(after: origin, seconds: idleBefore + activeSeconds)
    let finish = ticks(after: origin, seconds: idleBefore + activeSeconds + idleAfter)
    struct Header: Codable {
        let kind = "header"
        let schema = "native-pixel-session-energy-v1"
        let run_id: String
        let stamp: ClockStamp
        let pid: Int32
        let window_id: UInt32
        let route = "CGEvent.post cgSessionEventTap plus one CGWarpMouseCursorPosition; no delivery acknowledgement"
        let frozen_window: FrozenWindow
        let original_pointer_x: Double
        let original_pointer_y: Double
        let x: Double
        let y: Double
        let pixels: Int32
        let rate_hz: Int
        let expected_events: Int
        let characterize: Bool
        let initialize: Bool
        let origin_monotonic_ns: Double
        let active_start_monotonic_ns: Double
        let active_end_monotonic_ns: Double
        let finish_monotonic_ns: Double
        let posting = "CGEventPost cgSessionEventTap; request posting only, no app delivery acknowledgement"
        let phase_or_momentum_flags = "Unspecified/default; generated continuous pixel wheel events, not physical trackpad phases"
    }
    try emit(Header(run_id: runID, stamp: clockStamp(), pid: pid, window_id: windowID, frozen_window: frozen,
                    original_pointer_x: Double(originalPointer.x), original_pointer_y: Double(originalPointer.y), x: x, y: y,
                    pixels: pixels, rate_hz: rate, expected_events: count, characterize: characterize, initialize: initialize,
                    origin_monotonic_ns: Double(origin) * nsPerTick,
                    active_start_monotonic_ns: Double(activeStart) * nsPerTick,
                    active_end_monotonic_ns: Double(activeEnd) * nsPerTick,
                    finish_monotonic_ns: Double(finish) * nsPerTick))
    try notice("idle_before_begin", runID, "No events or app queries")
    try waitUntil(activeStart)
    try notice("idle_before_end", runID, "Still phase ended")
    try notice("active_begin", runID, "Absolute120Hz request schedule begins")
    for index in 0..<count {
        let deadline = ticks(after: activeStart, seconds: Double(index) / Double(rate))
        try waitUntil(deadline)
        try requireForeground(pid)
        guard try currentPointer() == point else { throw BenchFailure("Pointer changed; stop without overriding user") }
        let creationBegin = clockStamp()
        if creationBegin.monotonic_ns - Double(deadline) * nsPerTick > 50e6 {
            throw BenchFailure("Deadline index=\(index) exceeded50ms before creation; no stale request posted")
        }
        let delta: Int32 = initialize ? -pixels : ((index % periodEvents) < (periodEvents / 2) ? -pixels : pixels)
        guard let event = CGEvent(scrollWheelEvent2Source: nil, units: .pixel,
                                  wheelCount: 1, wheel1: delta, wheel2: 0, wheel3: 0) else {
            throw BenchFailure("CGEvent creation failed; incomplete attempt")
        }
        event.location = point
        event.flags = []
        event.setIntegerValueField(.scrollWheelEventIsContinuous, value: 1)
        // Session routing owns window annotations; retain constructor readbacks.
        let rawTarget = event.getIntegerValueField(.eventTargetUnixProcessID)
        let rawPointDelta = event.getIntegerValueField(.scrollWheelEventPointDeltaAxis1)
        let rawContinuous = event.getIntegerValueField(.scrollWheelEventIsContinuous)
        let begin = clockStamp()
        if begin.monotonic_ns - Double(deadline) * nsPerTick > 50e6 {
            throw BenchFailure("Deadline index=\(index) exceeded50ms before posting; no stale request posted")
        }
        event.post(tap: .cgSessionEventTap)
        let end = clockStamp()
        posted.append(PostedEvent(run_id: runID, index: index,
                                  scheduled_monotonic_ns: Double(deadline) * nsPerTick,
                                  pixel_delta_y: delta, creation_begin: creationBegin, begin: begin, end: end,
                                  start_lateness_ms: (begin.monotonic_ns - Double(deadline) * nsPerTick) / 1e6,
                                  target_pid_field: rawTarget, point_delta_y_field: rawPointDelta,
                                  continuous_field: rawContinuous))
        // Fail rather than issue a catch-up burst after a large scheduling stall.
        if begin.monotonic_ns - Double(deadline) * nsPerTick > 50e6 ||
           end.monotonic_ns - Double(deadline) * nsPerTick > 50e6 {
            throw BenchFailure("Post schedule exceeded50ms budget; retain invalid pair, no catch-up burst")
        }
    }
    try waitUntil(activeEnd)
    try notice("active_end", runID, "All requests returned; delivery unverified")
    try notice("idle_after_begin", runID, "No events or app queries")
    try waitUntil(finish)
    try notice("idle_after_end", runID, "Numeric phases ended; buffered event log follows")
    guard try currentPointer() == point else { throw BenchFailure("Pointer changed before numeric completion; preserve user position") }
    try requireWindow(pid, frozen, point)
    restorePointerIfUnchanged()
    guard !restorationFailed else { throw BenchFailure("Guarded pointer restoration failed; retain probe") }
    let cpuEnd = try processCPUNanoseconds()
    let observerEnd = clockStamp()
    guard cpuEnd >= cpuStart else { throw BenchFailure("Process CPU clock decreased") }
    for record in posted { try emit(record) }
    try emit(DriverAccounting(run_id: runID, cpu_start_ns: cpuStart, cpu_end_ns: cpuEnd, cpu_ns: cpuEnd - cpuStart,
                              observer_start: observerStart, observer_end: observerEnd))
    try notice("complete", runID, "Posted request count=\(posted.count); app output requires independent witness")
} catch {
    // No keys/buttons are held and no input taps or persistent services were created.
    // Preserve completed requests even when the remaining schedule is invalid.
    for record in posted { try? emit(record) }
    try? notice("failed", runID, String(describing: error))
    exit(2)
}
