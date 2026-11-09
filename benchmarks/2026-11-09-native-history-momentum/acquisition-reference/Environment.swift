import AppKit
import Foundation
import CoreGraphics

let process = ProcessInfo.processInfo
let app = NSWorkspace.shared.frontmostApplication
let pid = CommandLine.arguments.dropFirst().first.flatMap(Int32.init)
let windows = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String:Any]] ?? []).filter {
    ($0[kCGWindowOwnerPID as String] as? Int32) == pid && ($0[kCGWindowLayer as String] as? Int) == 0
}.map { row -> [String:Any] in
    return ["bounds": row[kCGWindowBounds as String] ?? [:], "alpha": row[kCGWindowAlpha as String] ?? 0, "onscreen":row[kCGWindowIsOnscreen as String] ?? false]
}
let screens = NSScreen.screens.map { screen -> [String:Any] in
    let id = (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0
    let mode = CGDisplayCopyDisplayMode(id)
    return ["id":id, "built_in":CGDisplayIsBuiltin(id), "frame":[screen.frame.origin.x,screen.frame.origin.y,screen.frame.width,screen.frame.height], "scale":screen.backingScaleFactor, "maximum_fps":screen.maximumFramesPerSecond, "mode_refresh_hz":mode?.refreshRate ?? 0, "pixel_width":mode?.pixelWidth ?? 0, "pixel_height":mode?.pixelHeight ?? 0]
}
let data: [String:Any] = ["unix_ms":Date().timeIntervalSince1970*1000, "thermal_state":process.thermalState.rawValue, "low_power_mode":process.isLowPowerModeEnabled, "reduce_motion":NSWorkspace.shared.accessibilityDisplayShouldReduceMotion, "frontmost_pid":app?.processIdentifier ?? 0, "frontmost_bundle":app?.bundleIdentifier ?? "", "screens":screens, "target_windows":windows]
print(String(data:try JSONSerialization.data(withJSONObject:data,options:[.sortedKeys]),encoding:.utf8)!)
