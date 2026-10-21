// Encodes one image to AVIF via macOS ImageIO. Used by scripts/build_images.py.
// Usage: avif_encode <input> <output> <quality 0..1>

import Foundation
import ImageIO

let args = CommandLine.arguments
guard args.count == 4, let quality = Double(args[3]) else {
    FileHandle.standardError.write("usage: avif_encode <in> <out> <quality>\n".data(using: .utf8)!)
    exit(64)
}

guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: args[1]) as CFURL, nil),
      let original = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    FileHandle.standardError.write("cannot read \(args[1])\n".data(using: .utf8)!)
    exit(65)
}

// Chrome decodes an ImageIO AVIF with an odd width or height as a fully
// transparent image (seen on 1280x853 photos in Chrome 152).
// Cropping the odd row or column away costs one pixel nobody will miss.
let evenWidth = original.width & ~1
let evenHeight = original.height & ~1
guard let image = original.cropping(to: CGRect(x: 0, y: 0, width: evenWidth, height: evenHeight)) else {
    FileHandle.standardError.write("cannot crop \(args[1]) to even dimensions\n".data(using: .utf8)!)
    exit(65)
}

guard let dest = CGImageDestinationCreateWithURL(
        URL(fileURLWithPath: args[2]) as CFURL, "public.avif" as CFString, 1, nil) else {
    FileHandle.standardError.write("no AVIF encoder on this system\n".data(using: .utf8)!)
    exit(69)
}

CGImageDestinationAddImage(dest, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
exit(CGImageDestinationFinalize(dest) ? 0 : 70)
