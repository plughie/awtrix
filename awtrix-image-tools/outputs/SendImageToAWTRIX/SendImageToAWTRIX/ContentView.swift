import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var showSender = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 18) {
                Image(systemName: "dotmatrix")
                    .font(.system(size: 52, weight: .regular))
                    .foregroundStyle(.tint)

                Text("Send Image to AWTRIX")
                    .font(.title2.weight(.semibold))

                Button {
                    showSender = true
                } label: {
                    Label("Open Sender", systemImage: "photo")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: 360)
            }
            .padding()
            .navigationTitle("Send Image to AWTRIX")
        }
        .sheet(isPresented: $showSender) {
            SenderView()
        }
    }
}

struct SenderView: View {
    private let appPrefix = "image_to_awtrix"

    @AppStorage("awtrixHost") private var host = ""
    @AppStorage("animationSeconds") private var animationSeconds = 8.0
    @AppStorage("scrollDirection") private var scrollDirectionRaw = ScrollDirection.topToBottom.rawValue
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var sourceImage: UIImage?
    @State private var cropRect = CGRect(x: 0.1, y: 0.1, width: 0.8, height: 0.8)
    @State private var pixelImage: PixelImage?
    @State private var isImportingFile = false
    @State private var isSending = false
    @State private var isCheckingConnection = false
    @State private var isConnected = false
    @State private var shouldLoop = false
    @State private var keepInRotation = false
    @State private var sendTask: Task<Void, Never>?
    @State private var status = "Connect to AWTRIX before choosing an image."

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    AwtrixAddressControl(host: $host)

                    Button {
                        Task { await connectToAwtrix() }
                    } label: {
                        if isCheckingConnection {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Label(isConnected ? "Connected" : "Connect", systemImage: isConnected ? "checkmark.circle.fill" : "network")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isSending || isCheckingConnection || host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    HStack(spacing: 12) {
                        PhotosPicker(selection: $selectedPhoto, matching: .images) {
                            Label("Photos", systemImage: "photo.on.rectangle")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!isConnected || isSending)

                        Button {
                            isImportingFile = true
                        } label: {
                            Label("Files", systemImage: "folder")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!isConnected || isSending)
                    }

                    Text(status)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    if let sourceImage {
                        ImageCropper(image: sourceImage, cropRect: $cropRect)

                        Button {
                            convertCrop()
                        } label: {
                            Label("Convert Crop", systemImage: "crop")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }

                    PixelPreview(pixelImage: pixelImage)
                        .frame(maxWidth: .infinity)

                    Toggle("Loop until stopped", isOn: $shouldLoop)
                        .disabled(isSending)

                    Toggle("Keep in app rotation", isOn: $keepInRotation)
                        .disabled(isSending)

                    Stepper(value: $animationSeconds, in: 1...120, step: 1) {
                        Label("Cycle Time: \(Int(animationSeconds)) seconds", systemImage: "timer")
                    }
                    .disabled(isSending)

                    Picker("Direction", selection: $scrollDirectionRaw) {
                        ForEach(ScrollDirection.allCases) { direction in
                            Text(direction.label).tag(direction.rawValue)
                        }
                    }
                    .pickerStyle(.menu)
                    .disabled(isSending)

                    Button {
                        if isSending {
                            Task { await stopAnimation() }
                        } else {
                            sendTask = Task { await sendImage() }
                        }
                    } label: {
                        if isSending {
                            Label("Stop Animation", systemImage: "stop.fill")
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("Upload and Run", systemImage: "paperplane.fill")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(pixelImage == nil || !isConnected || host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding()
                .frame(maxWidth: 620)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Send Image to AWTRIX")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        dismiss()
                    }
                    .disabled(isSending)
                }
            }
        }
        .onChange(of: selectedPhoto) { _, item in
            Task { await loadPhoto(item) }
        }
        .onChange(of: host) { _, _ in
            isConnected = false
            pixelImage = nil
            sourceImage = nil
            status = "Connect to AWTRIX before choosing an image."
        }
        .fileImporter(isPresented: $isImportingFile, allowedContentTypes: [.image]) { result in
            Task { await loadFile(result) }
        }
    }

    @Environment(\.dismiss) private var dismiss

    @MainActor
    private func connectToAwtrix() async {
        isCheckingConnection = true
        isConnected = false
        status = "Checking AWTRIX connection..."
        defer { isCheckingConnection = false }

        do {
            let client = AwtrixClient(host: host.trimmingCharacters(in: .whitespacesAndNewlines), appPrefix: appPrefix)
            try await client.prepareForUpload(keepInRotation: keepInRotation)
            isConnected = true
            status = "Connected. Choose an image."
        } catch {
            status = "Connection failed: \(error.localizedDescription)"
        }
    }

    private func loadPhoto(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        do {
            guard let data = try await item.loadTransferable(type: Data.self),
                  let image = ImageProcessor.loadImage(from: data) else {
                status = "That image could not be converted."
                return
            }
            sourceImage = image
            pixelImage = nil
            cropRect = initialCropRect(for: image)
            status = "Adjust the crop rectangle, then convert it."
        } catch {
            status = "Photo load failed: \(error.localizedDescription)"
        }
    }

    private func loadFile(_ result: Result<URL, Error>) async {
        do {
            let url = try result.get()
            guard url.startAccessingSecurityScopedResource() else {
                status = "File access was not granted."
                return
            }
            defer { url.stopAccessingSecurityScopedResource() }

            let data = try Data(contentsOf: url)
            guard let image = ImageProcessor.loadImage(from: data) else {
                status = "That file could not be converted."
                return
            }
            sourceImage = image
            pixelImage = nil
            cropRect = initialCropRect(for: image)
            status = "Adjust the crop rectangle, then convert it."
        } catch {
            status = "File load failed: \(error.localizedDescription)"
        }
    }

    private func convertCrop() {
        guard let sourceImage else { return }
        let imageSize = sourceImage.pixelSize
        let pixelCrop = CGRect(
            x: cropRect.minX * imageSize.width,
            y: cropRect.minY * imageSize.height,
            width: cropRect.width * imageSize.width,
            height: cropRect.height * imageSize.height
        )
        guard let pixels = ImageProcessor.makePixelImage(from: sourceImage, cropRect: pixelCrop) else {
            status = "That crop could not be converted."
            return
        }
        pixelImage = pixels
        status = "Ready: selected crop converted to 32x\(pixels.height)."
    }

    private func initialCropRect(for image: UIImage) -> CGRect {
        CGRect(x: 0.1, y: 0.1, width: 0.8, height: 0.8)
    }

    @MainActor
    private func sendImage() async {
        guard let pixelImage else { return }
        isSending = true
        status = "Uploading and running AWTRIX frames..."
        defer {
            isSending = false
            sendTask = nil
        }

        do {
            let client = AwtrixClient(host: host.trimmingCharacters(in: .whitespacesAndNewlines), appPrefix: appPrefix)
            let direction = ScrollDirection(rawValue: scrollDirectionRaw) ?? .topToBottom
            try await client.send(pixelImage: pixelImage, loop: shouldLoop, totalSeconds: animationSeconds, direction: direction, keepInRotation: keepInRotation)
            status = keepInRotation ? "Sent and kept in AWTRIX rotation." : (shouldLoop ? "Animation stopped." : "Sent and cleared from AWTRIX rotation.")
        } catch is CancellationError {
            status = "Animation stopped."
        } catch {
            status = "Send failed: \(error.localizedDescription)"
        }
    }

    @MainActor
    private func stopAnimation() async {
        sendTask?.cancel()
        status = "Stopping animation..."
        let client = AwtrixClient(host: host.trimmingCharacters(in: .whitespacesAndNewlines), appPrefix: appPrefix)
        try? await client.stop(keepInRotation: keepInRotation)
        isSending = false
        sendTask = nil
        status = "Animation stopped."
    }
}

private struct AwtrixAddressControl: View {
    @Binding var host: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("AWTRIX IP Address", systemImage: "network")
                .font(.headline)

            TextField("192.168.1.50", text: $host)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.numbersAndPunctuation)
                .textFieldStyle(.roundedBorder)
        }
    }
}

private struct ImageCropper: View {
    let image: UIImage
    @Binding var cropRect: CGRect
    @State private var dragStartRect = CGRect.zero

    var body: some View {
        GeometryReader { geometry in
            let imageFrame = fittedImageFrame(in: geometry.size)
            ZStack {
                Color.black

                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()

                cropOverlay(imageFrame: imageFrame)
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .gesture(moveGesture(imageFrame: imageFrame))
        }
        .aspectRatio(1, contentMode: .fit)
    }

    private func cropOverlay(imageFrame: CGRect) -> some View {
        let cropFrame = viewCropFrame(in: imageFrame)
        return ZStack {
            Path { path in
                path.addRect(imageFrame)
                path.addRect(cropFrame)
            }
            .fill(.black.opacity(0.58), style: FillStyle(eoFill: true))

            Path { path in
                path.addRect(cropFrame)
                let xThird = cropFrame.width / 3
                let yThird = cropFrame.height / 3
                path.move(to: CGPoint(x: cropFrame.minX + xThird, y: cropFrame.minY))
                path.addLine(to: CGPoint(x: cropFrame.minX + xThird, y: cropFrame.maxY))
                path.move(to: CGPoint(x: cropFrame.minX + xThird * 2, y: cropFrame.minY))
                path.addLine(to: CGPoint(x: cropFrame.minX + xThird * 2, y: cropFrame.maxY))
                path.move(to: CGPoint(x: cropFrame.minX, y: cropFrame.minY + yThird))
                path.addLine(to: CGPoint(x: cropFrame.maxX, y: cropFrame.minY + yThird))
                path.move(to: CGPoint(x: cropFrame.minX, y: cropFrame.minY + yThird * 2))
                path.addLine(to: CGPoint(x: cropFrame.maxX, y: cropFrame.minY + yThird * 2))
            }
            .stroke(.white.opacity(0.85), lineWidth: 1.5)

            ForEach(CropCorner.allCases, id: \.self) { corner in
                Circle()
                    .fill(.white)
                    .frame(width: 22, height: 22)
                    .position(corner.point(in: cropFrame))
                    .gesture(resizeGesture(corner: corner, imageFrame: imageFrame))
            }
        }
    }

    private func moveGesture(imageFrame: CGRect) -> some Gesture {
        DragGesture()
            .onChanged { value in
                if dragStartRect == .zero {
                    dragStartRect = cropRect
                }
                let dx = value.translation.width / max(1, imageFrame.width)
                let dy = value.translation.height / max(1, imageFrame.height)
                cropRect = constrainedRect(
                    CGRect(
                        x: dragStartRect.minX + dx,
                        y: dragStartRect.minY + dy,
                        width: dragStartRect.width,
                        height: dragStartRect.height
                    )
                )
            }
            .onEnded { _ in
                dragStartRect = .zero
            }
    }

    private func resizeGesture(corner: CropCorner, imageFrame: CGRect) -> some Gesture {
        DragGesture()
            .onChanged { value in
                if dragStartRect == .zero {
                    dragStartRect = cropRect
                }
                let dx = value.translation.width / max(1, imageFrame.width)
                let dy = value.translation.height / max(1, imageFrame.height)
                cropRect = constrainedRect(corner.rect(from: dragStartRect, dx: dx, dy: dy))
            }
            .onEnded { _ in
                dragStartRect = .zero
            }
    }

    private func fittedImageFrame(in container: CGSize) -> CGRect {
        let imageSize = image.pixelSize
        let scale = min(container.width / imageSize.width, container.height / imageSize.height)
        let width = imageSize.width * scale
        let height = imageSize.height * scale
        return CGRect(x: (container.width - width) / 2, y: (container.height - height) / 2, width: width, height: height)
    }

    private func viewCropFrame(in imageFrame: CGRect) -> CGRect {
        CGRect(
            x: imageFrame.minX + cropRect.minX * imageFrame.width,
            y: imageFrame.minY + cropRect.minY * imageFrame.height,
            width: cropRect.width * imageFrame.width,
            height: cropRect.height * imageFrame.height
        )
    }

    private func constrainedRect(_ rect: CGRect) -> CGRect {
        let minSize: CGFloat = 0.08
        let width = min(max(minSize, rect.width), 1)
        let height = min(max(minSize, rect.height), 1)
        let x = min(max(0, rect.minX), 1 - width)
        let y = min(max(0, rect.minY), 1 - height)
        return CGRect(x: x, y: y, width: width, height: height)
    }
}

private enum CropCorner: CaseIterable {
    case topLeft
    case topRight
    case bottomLeft
    case bottomRight

    func point(in rect: CGRect) -> CGPoint {
        switch self {
        case .topLeft:
            return CGPoint(x: rect.minX, y: rect.minY)
        case .topRight:
            return CGPoint(x: rect.maxX, y: rect.minY)
        case .bottomLeft:
            return CGPoint(x: rect.minX, y: rect.maxY)
        case .bottomRight:
            return CGPoint(x: rect.maxX, y: rect.maxY)
        }
    }

    func rect(from rect: CGRect, dx: CGFloat, dy: CGFloat) -> CGRect {
        switch self {
        case .topLeft:
            return CGRect(x: rect.minX + dx, y: rect.minY + dy, width: rect.width - dx, height: rect.height - dy)
        case .topRight:
            return CGRect(x: rect.minX, y: rect.minY + dy, width: rect.width + dx, height: rect.height - dy)
        case .bottomLeft:
            return CGRect(x: rect.minX + dx, y: rect.minY, width: rect.width - dx, height: rect.height + dy)
        case .bottomRight:
            return CGRect(x: rect.minX, y: rect.minY, width: rect.width + dx, height: rect.height + dy)
        }
    }
}

private struct PixelPreview: View {
    var pixelImage: PixelImage?

    var body: some View {
        Group {
            if let pixelImage {
                let width = pixelImage.width
                let height = pixelImage.height
                Grid(horizontalSpacing: 1, verticalSpacing: 1) {
                    ForEach(0..<height, id: \.self) { row in
                        GridRow {
                            ForEach(0..<width, id: \.self) { column in
                                Rectangle()
                                    .fill(pixelImage.colors[row * pixelImage.width + column])
                                    .aspectRatio(1, contentMode: .fit)
                            }
                        }
                    }
                }
                .aspectRatio(CGFloat(width) / CGFloat(height), contentMode: .fit)
            } else {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(white: 0.08))
                    .frame(height: 96)
            }
        }
        .padding(10)
        .background(.black)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private extension UIImage {
    var pixelSize: CGSize {
        if let cgImage {
            return CGSize(width: cgImage.width, height: cgImage.height)
        }
        return CGSize(width: size.width * scale, height: size.height * scale)
    }
}
