import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var bluetooth = CoolLedxBluetoothClient()
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var isImportingFile = false
    @State private var sourceImage: UIImage?
    @State private var pixelImage: PixelImage?
    @State private var isUploading = false
    @State private var localStatus = "Choose a display, then choose an image."

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    connectionPanel

                    HStack(spacing: 12) {
                        PhotosPicker(selection: $selectedPhoto, matching: .images) {
                            Label("Photos", systemImage: "photo.on.rectangle")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!bluetooth.isConnected || isUploading)

                        Button {
                            isImportingFile = true
                        } label: {
                            Label("Files", systemImage: "folder")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(!bluetooth.isConnected || isUploading)
                    }

                    Button {
                        setTestPattern()
                    } label: {
                        Label("Use Test Pattern", systemImage: "rectangle.grid.2x2")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .disabled(!bluetooth.isConnected || isUploading)

                    if let sourceImage {
                        Image(uiImage: sourceImage)
                            .resizable()
                            .scaledToFit()
                            .frame(maxHeight: 180)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    }

                    PixelPreview(pixelImage: pixelImage)

                    Button {
                        Task { await uploadImage() }
                    } label: {
                        if isUploading {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("Upload to Display", systemImage: "paperplane.fill")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!bluetooth.isConnected || pixelImage == nil || isUploading)

                    Text(localStatus)
                        .font(.system(size: 15))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding()
                .frame(maxWidth: 620)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("SendImageToCooLED")
        }
        .font(.system(size: 17))
        .dynamicTypeSize(.medium)
        .onChange(of: selectedPhoto) { _, item in
            Task { await loadPhoto(item) }
        }
        .fileImporter(isPresented: $isImportingFile, allowedContentTypes: [.image]) { result in
            Task { await loadFile(result) }
        }
    }

    private var connectionPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(bluetooth.isConnected ? bluetooth.connectedDeviceName : "Bluetooth Display", systemImage: bluetooth.isConnected ? "checkmark.circle.fill" : "dot.radiowaves.left.and.right")
                    .font(.headline)
                Spacer()
                Button(bluetooth.isScanning ? "Stop" : "Scan") {
                    bluetooth.isScanning ? bluetooth.stopScan() : bluetooth.scan()
                }
                .buttonStyle(.bordered)
            }

            if !bluetooth.isConnected && !bluetooth.devices.isEmpty {
                VStack(spacing: 8) {
                    ForEach(bluetooth.devices) { device in
                        Button {
                            Task { await connect(to: device) }
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(device.name)
                                    Text(device.sizeLabel)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }

            Text(bluetooth.status)
                .font(.system(size: 15))
                .foregroundStyle(.secondary)

            if !bluetooth.diagnostics.isEmpty {
                Text(bluetooth.diagnostics)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
        .padding(14)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func connect(to device: CoolLedxDevice) async {
        do {
            try await bluetooth.connect(to: device)
            bluetooth.clearScannedDevices()
            localStatus = "Connected. Choose an image."
        } catch {
            localStatus = "Connection failed: \(error.localizedDescription)"
        }
    }

    private func loadPhoto(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        do {
            guard let data = try await item.loadTransferable(type: Data.self),
                  let image = ImageProcessor.loadImage(from: data) else {
                localStatus = "That image could not be converted."
                return
            }
            setImage(image)
        } catch {
            localStatus = "Photo load failed: \(error.localizedDescription)"
        }
    }

    private func loadFile(_ result: Result<URL, Error>) async {
        do {
            let url = try result.get()
            guard url.startAccessingSecurityScopedResource() else {
                localStatus = "File access was not granted."
                return
            }
            defer { url.stopAccessingSecurityScopedResource() }

            let data = try Data(contentsOf: url)
            guard let image = ImageProcessor.loadImage(from: data) else {
                localStatus = "That file could not be converted."
                return
            }
            setImage(image)
        } catch {
            localStatus = "File load failed: \(error.localizedDescription)"
        }
    }

    @MainActor
    private func setImage(_ image: UIImage) {
        sourceImage = image
        pixelImage = ImageProcessor.makePixelImage(from: image, width: bluetooth.displayWidth, height: bluetooth.displayHeight)
        if let pixelImage {
            localStatus = "Ready: converted to \(pixelImage.width)x\(pixelImage.height)."
        } else {
            localStatus = "That image could not be converted."
        }
    }

    @MainActor
    private func setTestPattern() {
        sourceImage = nil
        pixelImage = ImageProcessor.makeTestPattern(width: bluetooth.displayWidth, height: bluetooth.displayHeight)
        localStatus = "Ready: test pattern converted to \(bluetooth.displayWidth)x\(bluetooth.displayHeight)."
    }

    @MainActor
    private func uploadImage() async {
        guard let pixelImage else { return }
        isUploading = true
        defer { isUploading = false }

        do {
            try await bluetooth.upload(pixelImage: pixelImage)
            localStatus = "Uploaded to the CoolLEDX display."
        } catch {
            localStatus = "Upload failed: \(error.localizedDescription)"
        }
    }
}

private struct PixelPreview: View {
    var pixelImage: PixelImage?

    var body: some View {
        Group {
            if let pixelImage {
                Grid(horizontalSpacing: 1, verticalSpacing: 1) {
                    ForEach(0..<pixelImage.height, id: \.self) { row in
                        GridRow {
                            ForEach(0..<pixelImage.width, id: \.self) { column in
                                Rectangle()
                                    .fill(pixelImage.colors[row * pixelImage.width + column])
                                    .aspectRatio(1, contentMode: .fit)
                            }
                        }
                    }
                }
                .aspectRatio(CGFloat(pixelImage.width) / CGFloat(pixelImage.height), contentMode: .fit)
            } else {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(white: 0.08))
                    .aspectRatio(4, contentMode: .fit)
            }
        }
        .padding(10)
        .background(.black)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
