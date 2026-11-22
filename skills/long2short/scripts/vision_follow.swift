// Follow one object through a frame sequence with Apple Vision's tracker (on-device).
// usage: vision_follow <frames_dir> <seed_index> <x> <y> <w> <h>
//   seed box normalized, origin top-left, on frame number seed_index (0-based, sorted order);
//   tracks forward and backward from the seed. Prints JSON lines {i, cx, cy, conf}.
import Foundation
import Vision
import AppKit

let a = CommandLine.arguments
let dir = a[1]; let seed = Int(a[2])!
let bx = Double(a[3])!, by = Double(a[4])!, bw = Double(a[5])!, bh = Double(a[6])!
let files = try FileManager.default.contentsOfDirectory(atPath: dir).filter { $0.hasSuffix(".jpg") }.sorted()
func cg(_ i: Int) -> CGImage {
    NSImage(contentsOf: URL(fileURLWithPath: dir).appendingPathComponent(files[i]))!
        .cgImage(forProposedRect: nil, context: nil, hints: nil)!
}
var out: [Int: [Double]] = [:]
for order in [Array(seed..<files.count), Array((0...seed).reversed())] {
    var obs = VNDetectedObjectObservation(boundingBox: CGRect(x: bx, y: 1 - by - bh, width: bw, height: bh))
    let handler = VNSequenceRequestHandler()
    let req = VNTrackObjectRequest(detectedObjectObservation: obs)
    req.trackingLevel = .accurate
    var lost = 0
    for i in order {
        req.inputObservation = obs
        do { try handler.perform([req], on: cg(i)) } catch { FileHandle.standardError.write("err \(i): \(error)\n".data(using: .utf8)!); break }
        guard let r = req.results?.first as? VNDetectedObjectObservation else { break }
        if r.confidence < 0.25 { lost += 1; if lost > 3 { break }; continue }
        lost = 0
        obs = r
        let b = r.boundingBox
        out[i] = [Double(b.midX), Double(1 - b.midY), Double(r.confidence)]
    }
}
for i in out.keys.sorted() {
    let v = out[i]!
    print("{\"i\":\(i),\"cx\":\(v[0]),\"cy\":\(v[1]),\"conf\":\(v[2])}")
}
