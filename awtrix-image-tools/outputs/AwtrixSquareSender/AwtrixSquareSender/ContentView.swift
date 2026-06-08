import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var host = "192.168.8.99"
    @State private var appPrefix = "sacred_square_bar"
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var pixelImage: PixelImage?
    @State private var isImportingFile = false
    @State private var isSending = false
    @State private var status = "Choose a square-ish image."

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    PixelPreview(pixelImage: pixelImage)
                        .frame(maxWidth: .infinity)

                    HStack(spacing: 12) {
                        PhotosPicker(selection: $selectedPhoto, matching: .images) {
                            Label("Photos", systemImage: "photo.on.rectangle")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)

                        Button {
                            isImportingFile = true
                        } label: {
                            Label("Files", systemImage: "folder")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }

                    VStack(spacing: 12) {
                        TextField("AWTRIX IP", text: $host)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.numbersAndPunctuation)

                        TextField("App prefix", text: $appPrefix)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                    .textFieldStyle(.roundedBorder)

                    Button {
                        Task { await sendImage() }
                    } label: {
                        if isSending {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("Upload and Run", systemImage: "paperplane.fill")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(pixelImage == nil || isSending)

                    Text(status)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding()
            }
            .navigationTitle("AWTRIX Square")
        }
        .onChange(of: selectedPhoto) { _, item in
            Task { await loadPhoto(item) }
        }
        .fileImporter(isPresented: $isImportingFile, allowedContentTypes: [.image]) { result in
            Task { await loadFile(result) }
        }
    }

    private func loadPhoto(_ item: PhotosPickerItem?) async {
        guard let item else { return }
        do {
            guard let data = try await item.loadTransferable(type: Data.self),
                  let image = ImageProcessor.loadImage(from: data),
                  let pixels = ImageProcessor.makePixelImage(from: image) else {
                status = "That image could not be converted."
                return
            }
            pixelImage = pixels
            status = "Ready: cropped and converted to 32x32."
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
            guard let image = ImageProcessor.loadImage(from: data),
                  let pixels = ImageProcessor.makePixelImage(from: image) else {
                status = "That file could not be converted."
                return
            }
            pixelImage = pixels
            status = "Ready: cropped and converted to 32x32."
        } catch {
            status = "File load failed: \(error.localizedDescription)"
        }
    }

    private func sendImage() async {
        guard let pixelImage else { return }
        isSending = true
        status = "Uploading 8 AWTRIX frames..."
        defer { isSending = false }

        do {
            let client = AwtrixClient(host: host.trimmingCharacters(in: .whitespacesAndNewlines), appPrefix: appPrefix)
            try await client.upload(pixelImage: pixelImage)
            status = "Uploaded. Running once..."
            try await client.runOnce()
            status = "Sent to AWTRIX."
        } catch {
            status = "Send failed: \(error.localizedDescription)"
        }
    }
}

private struct PixelPreview: View {
    var pixelImage: PixelImage?

    var body: some View {
        Grid(horizontalSpacing: 1, verticalSpacing: 1) {
            ForEach(0..<32, id: \.self) { row in
                GridRow {
                    ForEach(0..<32, id: \.self) { column in
                        Rectangle()
                            .fill(color(row: row, column: column))
                            .aspectRatio(1, contentMode: .fit)
                    }
                }
            }
        }
        .padding(10)
        .background(.black)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .aspectRatio(1, contentMode: .fit)
    }

    private func color(row: Int, column: Int) -> Color {
        guard let pixelImage else { return Color(white: 0.08) }
        return pixelImage.colors[row * pixelImage.width + column]
    }
}
