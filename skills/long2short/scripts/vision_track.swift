// Detect faces and people in a list of frames with Apple Vision (on-device).
// usage: vision_track <frames_dir>   -> prints JSON lines {file, faces, humans, salient: [[x,y,w,h]]}
// Coordinates are normalized 0..1 with origin top-left.
import Foundation
import Vision
import AppKit

let dir = CommandLine.arguments[1]
let files = try FileManager.default.contentsOfDirectory(atPath: dir).filter { $0.hasSuffix(".jpg") }.sorted()
func box(_ r: CGRect) -> [Double] { [Double(r.minX), Double(1 - r.maxY), Double(r.width), Double(r.height)] }
for f in files {
    let url = URL(fileURLWithPath: dir).appendingPathComponent(f)
    guard let img = NSImage(contentsOf: url), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let faceReq = VNDetectFaceRectanglesRequest()
    let humanReq = VNDetectHumanRectanglesRequest()
    humanReq.upperBodyOnly = true
    let salReq = VNGenerateObjectnessBasedSaliencyImageRequest()
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    try? h.perform([faceReq, humanReq, salReq])
    let sal = ((salReq.results?.first as? VNSaliencyImageObservation)?.salientObjects ?? []).map { box($0.boundingBox) }
    let faces = (faceReq.results ?? []).filter { $0.confidence > 0.5 }.map { box($0.boundingBox) }
    let humans = (humanReq.results ?? []).filter { $0.confidence > 0.5 }.map { box($0.boundingBox) }
    let obj: [String: Any] = ["file": f, "faces": faces, "humans": humans, "salient": sal]
    let data = try JSONSerialization.data(withJSONObject: obj)
    print(String(data: data, encoding: .utf8)!)
}
