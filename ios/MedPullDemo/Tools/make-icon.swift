// Draws MedPull Demo's app icon: the real app's icon with a "DEMO" band
// across the bottom, so the two apps cannot be mistaken for each other on a
// home screen. Run from anywhere:
//
//     swift ios/MedPullDemo/Tools/make-icon.swift
//
// It reads the three 1024pt icons of the real app
// (ios/MedPull/Assets.xcassets/AppIcon.appiconset) and writes the three of
// the demo (ios/MedPullDemo/Demo.xcassets/AppIconDemo.appiconset). Re-run it
// whenever the real icon changes. macOS only; nothing here ships in the app.

import AppKit
import CoreGraphics
import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers

let tools = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
let ios = tools.deletingLastPathComponent().deletingLastPathComponent()
let source = ios.appendingPathComponent("MedPull/Assets.xcassets/AppIcon.appiconset")
let target = ios.appendingPathComponent("MedPullDemo/Demo.xcassets/AppIconDemo.appiconset")
let fontFile = ios.appendingPathComponent("MedPull/Resources/Fonts/Outfit-Medium.ttf")

/// One appearance of the icon: the file it is drawn from, the file it is
/// written to, and the band's two colours. The band is the app's primary
/// capsule: near-black with white letters in light, inverted in dark, and a
/// plain grey for the tinted (greyscale) icon the system recolours.
struct Variant {
    let from: String
    let to: String
    let band: (CGFloat, CGFloat, CGFloat)
    let ink: (CGFloat, CGFloat, CGFloat)
    let dot: (CGFloat, CGFloat, CGFloat)?
}

let lime: (CGFloat, CGFloat, CGFloat) = (212, 241, 74)
let variants = [
    Variant(from: "AppIcon-1024.png", to: "AppIconDemo-1024.png",
            band: (20, 20, 20), ink: (255, 255, 255), dot: lime),
    Variant(from: "AppIcon-1024-dark.png", to: "AppIconDemo-1024-dark.png",
            band: (245, 245, 247), ink: (20, 20, 20), dot: nil),
    Variant(from: "AppIcon-1024-tinted.png", to: "AppIconDemo-1024-tinted.png",
            band: (96, 96, 96), ink: (255, 255, 255), dot: nil),
]

func color(_ c: (CGFloat, CGFloat, CGFloat)) -> CGColor {
    CGColor(srgbRed: c.0 / 255, green: c.1 / 255, blue: c.2 / 255, alpha: 1)
}

guard CTFontManagerRegisterFontsForURL(fontFile as CFURL, .process, nil) else {
    fatalError("Could not load \(fontFile.path)")
}

let side = 1024
/// The band's height, and how far the mark moves up to clear it.
let bandHeight: CGFloat = 212
let lift: CGFloat = 78

for variant in variants {
    let input = source.appendingPathComponent(variant.from)
    guard let provider = CGDataProvider(url: input as CFURL),
          let image = CGImage(pngDataProviderSource: provider, decode: nil,
                              shouldInterpolate: true, intent: .defaultIntent) else {
        fatalError("Could not read \(input.path)")
    }
    // Opaque RGB: App Store Connect refuses an icon with an alpha channel.
    guard let ctx = CGContext(data: nil, width: side, height: side, bitsPerComponent: 8,
                              bytesPerRow: 0, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else {
        fatalError("No drawing context")
    }
    let full = CGRect(x: 0, y: 0, width: side, height: side)
    // The original as the ground (its corners and gradient), then again
    // moved up, so the mark sits above the band. CoreGraphics' origin is
    // the bottom left: up is +y.
    ctx.draw(image, in: full)
    ctx.draw(image, in: full.offsetBy(dx: 0, dy: lift))
    ctx.setFillColor(color(variant.band))
    ctx.fill(CGRect(x: 0, y: 0, width: CGFloat(side), height: bandHeight))

    // "DEMO", tracked out, centred in the band, with the lime dot the
    // primary button carries (light icon only).
    let font = CTFontCreateWithName("Outfit-Medium" as CFString, 112, nil)
    let text = NSAttributedString(string: "DEMO", attributes: [
        .font: font,
        .foregroundColor: NSColor(cgColor: color(variant.ink))!,
        .kern: 22,
    ])
    let line = CTLineCreateWithAttributedString(text)
    let bounds = CTLineGetBoundsWithOptions(line, .useGlyphPathBounds)
    let dotSide: CGFloat = variant.dot == nil ? 0 : 32
    let gap: CGFloat = variant.dot == nil ? 0 : 44
    // The trailing kern is not ink: leave it out of the centring.
    let inkWidth = bounds.width - 22
    let total = dotSide + gap + inkWidth
    let startX = (CGFloat(side) - total) / 2
    let baseline = (bandHeight - bounds.height) / 2 - bounds.minY + 4
    if let dot = variant.dot {
        ctx.setFillColor(color(dot))
        ctx.fillEllipse(in: CGRect(x: startX, y: baseline + bounds.height / 2 - dotSide / 2 + bounds.minY,
                                   width: dotSide, height: dotSide))
    }
    ctx.textPosition = CGPoint(x: startX + dotSide + gap - bounds.minX, y: baseline)
    CTLineDraw(line, ctx)

    guard let output = ctx.makeImage() else { fatalError("No image") }
    let file = target.appendingPathComponent(variant.to)
    guard let destination = CGImageDestinationCreateWithURL(file as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        fatalError("Could not write \(file.path)")
    }
    CGImageDestinationAddImage(destination, output, nil)
    guard CGImageDestinationFinalize(destination) else { fatalError("Could not write \(file.path)") }
    print("wrote \(file.path)")
}
