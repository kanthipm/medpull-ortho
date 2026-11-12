// Draws the small clip MedPull Demo carries as its "sample clip": three
// seconds of a line figure doing two squats, with the words "Sample clip" on
// every frame so nobody on either side of the demo takes it for a person's
// own recording. Run from anywhere:
//
//     swift ios/MedPullDemo/Tools/make-sample-clip.swift
//
// It writes ios/MedPullDemo/Resources/sample-attempt.mp4 (H.264 in MP4, the
// index at the front, about 100 KB). The guided session offers it on a demo
// server when the exercise has no clip of the therapist's to stand in, and a
// simulator has no camera to record with. macOS only; the script does not
// ship in the app.

import AVFoundation
import AppKit
import CoreGraphics
import CoreText
import CoreVideo
import Foundation

let tools = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
let ios = tools.deletingLastPathComponent().deletingLastPathComponent()
let output = ios.appendingPathComponent("MedPullDemo/Resources/sample-attempt.mp4")
let fontFile = ios.appendingPathComponent("MedPull/Resources/Fonts/Outfit-Medium.ttf")

let width = 480, height = 640
let fps: Int32 = 30
let seconds = 3.0
let frames = Int(seconds * Double(fps))

guard CTFontManagerRegisterFontsForURL(fontFile as CFURL, .process, nil) else {
    fatalError("Could not load \(fontFile.path)")
}
try? FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
try? FileManager.default.removeItem(at: output)

let writer = try AVAssetWriter(outputURL: output, fileType: .mp4)
writer.shouldOptimizeForNetworkUse = true
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: width,
    AVVideoHeightKey: height,
    AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: 260_000,
        AVVideoMaxKeyFrameIntervalKey: 30,
        AVVideoProfileLevelKey: AVVideoProfileLevelH264MainAutoLevel,
    ],
])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
    kCVPixelBufferWidthKey as String: width,
    kCVPixelBufferHeightKey as String: height,
])
writer.add(input)
guard writer.startWriting() else { fatalError("Could not start: \(String(describing: writer.error))") }
writer.startSession(atSourceTime: .zero)

func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: r / 255, green: g / 255, blue: b / 255, alpha: a)
}

let ink = color(20, 20, 20)
let canvas = color(251, 251, 249)
let rule = color(138, 140, 136)

/// One frame: the floor, the figure and the words, and nothing that could
/// be read as a measurement of the movement. `depth` is 0 standing and 1 at
/// the bottom of the squat.
func draw(_ ctx: CGContext, depth d: CGFloat) {
    let w = CGFloat(width), h = CGFloat(height)
    // A top-left origin, like the screen the clip is watched on.
    ctx.translateBy(x: 0, y: h)
    ctx.scaleBy(x: 1, y: -1)
    ctx.setFillColor(canvas)
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))

    // The floor.
    let floor: CGFloat = 520
    ctx.setStrokeColor(rule)
    ctx.setLineWidth(2)
    ctx.move(to: CGPoint(x: 60, y: floor))
    ctx.addLine(to: CGPoint(x: w - 60, y: floor))
    ctx.strokePath()

    // The figure, from the side: ankle fixed, the knee travelling forward
    // and the hips back and down, the trunk leaning to balance.
    let ankle = CGPoint(x: 232, y: floor - 6)
    let knee = CGPoint(x: ankle.x + 6 + 44 * d, y: ankle.y - 108 + 14 * d)
    let hip = CGPoint(x: ankle.x - 8 - 58 * d, y: ankle.y - 216 + 104 * d)
    let lean = (6 + 30 * d) * CGFloat.pi / 180
    let shoulder = CGPoint(x: hip.x + sin(lean) * 124, y: hip.y - cos(lean) * 124)
    let head = CGPoint(x: shoulder.x + sin(lean) * 34, y: shoulder.y - cos(lean) * 34)
    let hand = CGPoint(x: shoulder.x + 66 + 22 * d, y: shoulder.y + 34 - 28 * d)
    let toe = CGPoint(x: ankle.x + 44, y: floor - 2)

    ctx.setStrokeColor(ink)
    ctx.setLineWidth(13)
    ctx.setLineCap(.round)
    ctx.setLineJoin(.round)
    for (from, to) in [(toe, ankle), (ankle, knee), (knee, hip), (hip, shoulder), (shoulder, hand)] {
        ctx.move(to: from)
        ctx.addLine(to: to)
    }
    ctx.strokePath()
    ctx.setFillColor(ink)
    ctx.fillEllipse(in: CGRect(x: head.x - 24, y: head.y - 24, width: 48, height: 48))

    // The words, on every frame. Text is drawn in CoreText's own upright
    // space, so the flip is undone around it.
    func text(_ string: String, size: CGFloat, at point: CGPoint, color: CGColor) {
        let font = CTFontCreateWithName("Outfit-Medium" as CFString, size, nil)
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: string, attributes: [
            .font: font, .foregroundColor: NSColor(cgColor: color)!, .kern: -0.4,
        ]))
        ctx.saveGState()
        ctx.translateBy(x: point.x, y: point.y)
        ctx.scaleBy(x: 1, y: -1)
        ctx.textPosition = .zero
        CTLineDraw(line, ctx)
        ctx.restoreGState()
    }
    text("Sample clip", size: 34, at: CGPoint(x: 36, y: 70), color: ink)
    text("MedPull Demo  ·  not a person’s recording", size: 17, at: CGPoint(x: 36, y: 100), color: color(88, 91, 88))
}

for frame in 0..<frames {
    while !input.isReadyForMoreMediaData { Thread.sleep(forTimeInterval: 0.005) }
    guard let pool = adaptor.pixelBufferPool else { fatalError("No pixel buffer pool") }
    var made: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, pool, &made)
    guard let buffer = made else { fatalError("No pixel buffer") }
    CVPixelBufferLockBaseAddress(buffer, [])
    guard let ctx = CGContext(
        data: CVPixelBufferGetBaseAddress(buffer), width: width, height: height, bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buffer), space: CGColorSpace(name: CGColorSpace.sRGB)!,
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
    ) else { fatalError("No drawing context") }
    // Two squats in the three seconds, eased at the top and the bottom.
    let t = Double(frame) / Double(frames) * 2
    let depth = 0.5 - 0.5 * cos(2 * Double.pi * t)
    draw(ctx, depth: CGFloat(depth))
    CVPixelBufferUnlockBaseAddress(buffer, [])
    guard adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: fps)) else {
        fatalError("Could not append frame \(frame): \(String(describing: writer.error))")
    }
}

input.markAsFinished()
let finished = DispatchSemaphore(value: 0)
writer.finishWriting { finished.signal() }
finished.wait()
guard writer.status == .completed else { fatalError("Not written: \(String(describing: writer.error))") }
// The writer can leave its scratch file beside the output.
let folder = output.deletingLastPathComponent()
for stray in (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []
where stray.lastPathComponent.hasPrefix(output.lastPathComponent + ".sb-") {
    try? FileManager.default.removeItem(at: stray)
}
let size = (try? FileManager.default.attributesOfItem(atPath: output.path)[.size] as? Int) ?? 0
print("wrote \(output.path) (\(size / 1024) KB)")
