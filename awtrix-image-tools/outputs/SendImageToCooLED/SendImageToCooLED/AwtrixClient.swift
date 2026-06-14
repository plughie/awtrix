import CoreBluetooth
import Foundation

struct CoolLedxDevice: Identifiable, Equatable {
    let id: UUID
    let name: String
    let width: Int
    let height: Int
    fileprivate let peripheral: CBPeripheral

    var sizeLabel: String {
        "\(width)x\(height)"
    }
}

private struct CoolLedxDeviceDimensions {
    let width: Int
    let height: Int

    static func from(advertisementData: [String: Any]) -> CoolLedxDeviceDimensions {
        guard let manufacturerData = advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data else {
            return CoolLedxDeviceDimensions(width: 64, height: 16)
        }

        let candidates = [
            dimensions(from: manufacturerData, heightIndex: 6, widthIndex: 8),
            dimensions(from: manufacturerData, heightIndex: 8, widthIndex: 10)
        ]

        if let dimensions = candidates.compactMap({ $0 }).first {
            return dimensions
        }

        return CoolLedxDeviceDimensions(width: 64, height: 16)
    }

    private static func dimensions(from data: Data, heightIndex: Int, widthIndex: Int) -> CoolLedxDeviceDimensions? {
        guard data.count > widthIndex else { return nil }
        let height = Int(data[heightIndex])
        let width = Int(data[widthIndex])
        let knownHeights = [8, 16, 32, 64]
        let knownWidths = [16, 32, 64, 96, 128]

        guard knownHeights.contains(height),
              knownWidths.contains(width),
              width >= height,
              width * height <= 8192 else {
            return nil
        }

        return CoolLedxDeviceDimensions(width: width, height: height)
    }
}

@MainActor
final class CoolLedxBluetoothClient: NSObject, ObservableObject {
    @Published var devices: [CoolLedxDevice] = []
    @Published var connectedDeviceName = ""
    @Published var displayWidth = 64
    @Published var displayHeight = 16
    @Published var isScanning = false
    @Published var isConnected = false
    @Published var status = "Turn on Bluetooth and scan for the CoolLEDX display."
    @Published var diagnostics = ""

    private var central: CBCentralManager!
    private var connectedPeripheral: CBPeripheral?
    private var writableCharacteristic: CBCharacteristic?
    private var pendingCharacteristicServices = Set<String>()
    private var pendingContinuation: CheckedContinuation<Void, Error>?
    private var writeContinuation: CheckedContinuation<Void, Error>?
    private var notifyContinuation: CheckedContinuation<Bool, Never>?
    private var readContinuation: CheckedContinuation<Data?, Never>?
    private var pendingNotifyAcknowledged = false
    private var waitingForNotificationSetup = false
    private var notificationsEnabled = false
    private var connectionDiagnostics = ""
    private let writeWithoutResponseFragmentSize = 20
    private let writeWithoutResponseFragmentDelay: UInt64 = 45_000_000
    private let writeWithoutResponseCommandDelay: UInt64 = 300_000_000

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
    }

    func scan() {
        devices.removeAll()
        isConnected = false
        writableCharacteristic = nil
        pendingCharacteristicServices.removeAll()
        waitingForNotificationSetup = false
        notificationsEnabled = false
        connectionDiagnostics = ""
        diagnostics = ""

        guard central.state == .poweredOn else {
            status = "Bluetooth is not ready yet."
            return
        }

        status = "Scanning for nearby Bluetooth displays..."
        isScanning = true
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    func stopScan() {
        central.stopScan()
        isScanning = false
    }

    func clearScannedDevices() {
        devices.removeAll()
    }

    func connect(to device: CoolLedxDevice) async throws {
        stopScan()
        status = "Connecting to \(device.name)..."
        displayWidth = device.width
        displayHeight = device.height
        connectedPeripheral = device.peripheral
        connectedPeripheral?.delegate = self
        central.connect(device.peripheral, options: nil)
        try await waitForBluetoothStep()
    }

    func disconnect() {
        if let connectedPeripheral {
            central.cancelPeripheralConnection(connectedPeripheral)
        }
        connectedPeripheral = nil
        writableCharacteristic = nil
        pendingCharacteristicServices.removeAll()
        waitingForNotificationSetup = false
        notificationsEnabled = false
        connectionDiagnostics = ""
        connectedDeviceName = ""
        displayWidth = 64
        displayHeight = 16
        isConnected = false
        status = "Disconnected."
        diagnostics = ""
    }

    func upload(pixelImage: PixelImage) async throws {
        guard let peripheral = connectedPeripheral, let characteristic = writableCharacteristic else {
            throw CoolLedxBluetoothError.notConnected
        }

        let chunks = CoolLedxPacketBuilder.imageCommandChunks(pixelImage: pixelImage)
        let writeMode = characteristic.properties.contains(.write) ? "with response" : "without response"
        let shouldWaitForAcknowledgement = characteristic.properties.contains(.write) && notificationsEnabled
        status = "Uploading \(pixelImage.width)x\(pixelImage.height), \(chunks.count) image chunks, \(writeMode)..."
        let fragmentNote = characteristic.properties.contains(.write) ? "" : ", \(writeWithoutResponseFragmentSize)-byte fragments, slow pacing"
        let ackNote = shouldWaitForAcknowledgement ? "ack on" : "ack not available"
        diagnostics = "\(connectionDiagnostics)\nUpload: \(pixelImage.width)x\(pixelImage.height), \(chunks.count) chunks, \(writeMode)\(fragmentNote), \(ackNote)"

        for (index, chunk) in chunks.enumerated() {
            try Task.checkCancellation()
            let writeType: CBCharacteristicWriteType = characteristic.properties.contains(.write) ? .withResponse : .withoutResponse
            status = "Uploading image chunk \(index + 1) of \(chunks.count) (\(chunk.count) bytes)..."
            let fragmentCount = writeType == .withoutResponse ? Int(ceil(Double(chunk.count) / Double(writeWithoutResponseFragmentSize))) : 1
            diagnostics = "\(connectionDiagnostics)\nChunk \(index + 1)/\(chunks.count): \(chunk.count) bytes, \(fragmentCount) BLE writes, first bytes \(chunk.hexPrefix())"
            pendingNotifyAcknowledged = false
            try await write(chunk, to: characteristic, on: peripheral, writeType: writeType)
            if shouldWaitForAcknowledgement {
                try await waitForNotify(chunkIndex: index + 1, totalChunks: chunks.count, timeoutNanoseconds: 2_000_000_000)
            } else if !notificationsEnabled && !characteristic.properties.contains(.write) {
                throw CoolLedxBluetoothError.notificationsUnavailable
            }
        }

        let readBack = characteristic.properties.contains(.read) ? await readValue(from: characteristic, on: peripheral) : nil
        status = shouldWaitForAcknowledgement ? "Upload complete." : "Upload sent; display did not provide acknowledgements."
        let readBackText = readBack.map { " Read: \($0.hexPrefix(maxBytes: 20))" } ?? ""
        diagnostics = "\(connectionDiagnostics)\nSent \(chunks.count) image chunks. \(shouldWaitForAcknowledgement ? "Display acknowledged upload." : "No acknowledgement available on this iOS write path.")\(readBackText)"
    }

    private func waitForBluetoothStep() async throws {
        try await withCheckedThrowingContinuation { continuation in
            pendingContinuation = continuation
        }
    }

    private func resumePending(_ result: Result<Void, Error>) {
        guard let pendingContinuation else { return }
        self.pendingContinuation = nil
        switch result {
        case .success:
            pendingContinuation.resume()
        case .failure(let error):
            pendingContinuation.resume(throwing: error)
        }
    }

    private func write(_ chunk: Data, to characteristic: CBCharacteristic, on peripheral: CBPeripheral, writeType: CBCharacteristicWriteType) async throws {
        switch writeType {
        case .withResponse:
            try await withCheckedThrowingContinuation { continuation in
                writeContinuation = continuation
                peripheral.writeValue(chunk, for: characteristic, type: .withResponse)
            }
        case .withoutResponse:
            var offset = 0
            while offset < chunk.count {
                try Task.checkCancellation()
                while !peripheral.canSendWriteWithoutResponse {
                    try Task.checkCancellation()
                    try await Task.sleep(nanoseconds: 20_000_000)
                }

                let end = min(offset + writeWithoutResponseFragmentSize, chunk.count)
                peripheral.writeValue(chunk.subdata(in: offset..<end), for: characteristic, type: .withoutResponse)
                offset = end
                try await Task.sleep(nanoseconds: writeWithoutResponseFragmentDelay)
            }
            try await Task.sleep(nanoseconds: writeWithoutResponseCommandDelay)
        @unknown default:
            peripheral.writeValue(chunk, for: characteristic, type: .withResponse)
            try await Task.sleep(nanoseconds: 90_000_000)
        }
    }

    private func resumeWrite(_ result: Result<Void, Error>) {
        guard let writeContinuation else { return }
        self.writeContinuation = nil
        switch result {
        case .success:
            writeContinuation.resume()
        case .failure(let error):
            writeContinuation.resume(throwing: error)
        }
    }

    private func readValue(from characteristic: CBCharacteristic, on peripheral: CBPeripheral) async -> Data? {
        await withTaskGroup(of: Data?.self) { group in
            group.addTask { @MainActor in
                await withCheckedContinuation { continuation in
                    self.readContinuation = continuation
                    peripheral.readValue(for: characteristic)
                }
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                return nil
            }
            let value = await group.next() ?? nil
            self.readContinuation?.resume(returning: nil)
            self.readContinuation = nil
            group.cancelAll()
            return value
        }
    }

    private func waitForNotify(chunkIndex: Int, totalChunks: Int, timeoutNanoseconds: UInt64) async throws {
        if pendingNotifyAcknowledged {
            pendingNotifyAcknowledged = false
            return
        }

        let acknowledged = await withTaskGroup(of: Bool.self) { group in
            group.addTask { @MainActor in
                await withCheckedContinuation { continuation in
                    self.notifyContinuation = continuation
                }
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: timeoutNanoseconds)
                return false
            }
            let result = await group.next() ?? false
            self.notifyContinuation?.resume(returning: false)
            self.notifyContinuation = nil
            group.cancelAll()
            return result
        }

        if !acknowledged {
            throw CoolLedxBluetoothError.displayDidNotAcknowledge(chunkIndex: chunkIndex, totalChunks: totalChunks)
        }
    }

    private func resumeNotify() {
        if let notifyContinuation {
            notifyContinuation.resume(returning: true)
            self.notifyContinuation = nil
        } else {
            pendingNotifyAcknowledged = true
        }
    }

    private func markConnected(to peripheral: CBPeripheral) {
        connectedDeviceName = peripheral.name ?? "CoolLEDX display"
        isConnected = true
        status = "Connected to \(connectedDeviceName) (\(displayWidth)x\(displayHeight)). Choose an image."
        resumePending(.success(()))
    }
}

extension CoolLedxBluetoothClient: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        Task { @MainActor in
            switch central.state {
            case .poweredOn:
                status = "Bluetooth is ready. Scan for the display."
            case .poweredOff:
                status = "Bluetooth is off."
            case .unauthorized:
                status = "Bluetooth permission was not granted."
            case .unsupported:
                status = "Bluetooth is not supported on this device."
            default:
                status = "Bluetooth is not ready yet."
            }
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        Task { @MainActor in
            let advertisedName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
            let name = advertisedName ?? peripheral.name ?? "Unnamed display"
            let dimensions = CoolLedxDeviceDimensions.from(advertisementData: advertisementData)
            let device = CoolLedxDevice(id: peripheral.identifier, name: name, width: dimensions.width, height: dimensions.height, peripheral: peripheral)
            if !devices.contains(where: { $0.id == device.id }) {
                devices.append(device)
            }
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        Task { @MainActor in
            status = "Discovering display services..."
            peripheral.discoverServices(nil)
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            resumePending(.failure(error ?? CoolLedxBluetoothError.connectionFailed))
        }
    }

    nonisolated func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            isConnected = false
            writableCharacteristic = nil
            pendingCharacteristicServices.removeAll()
            waitingForNotificationSetup = false
            notificationsEnabled = false
            connectionDiagnostics = ""
            connectedDeviceName = ""
            if let error {
                status = "Disconnected: \(error.localizedDescription)"
            }
        }
    }
}

extension CoolLedxBluetoothClient: CBPeripheralDelegate {
    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        Task { @MainActor in
            if let error {
                resumePending(.failure(error))
                return
            }
            guard let services = peripheral.services, !services.isEmpty else {
                resumePending(.failure(CoolLedxBluetoothError.noServices))
                return
            }
            pendingCharacteristicServices = Set(services.map { $0.uuid.uuidString })
            services.forEach { peripheral.discoverCharacteristics(nil, for: $0) }
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        Task { @MainActor in
            if let error {
                resumePending(.failure(error))
                return
            }
            pendingCharacteristicServices.remove(service.uuid.uuidString)
            guard writableCharacteristic == nil else { return }
            let preferredUUID = CBUUID(string: CoolLedxPacketBuilder.characteristicUUID)
            guard let characteristic = service.characteristics?.first(where: { $0.uuid == preferredUUID && ($0.properties.contains(.write) || $0.properties.contains(.writeWithoutResponse)) }) else {
                if pendingCharacteristicServices.isEmpty {
                    resumePending(.failure(CoolLedxBluetoothError.noCoolLedCharacteristic))
                }
                return
            }

            writableCharacteristic = characteristic
            let maxResponse = peripheral.maximumWriteValueLength(for: .withResponse)
            let maxNoResponse = peripheral.maximumWriteValueLength(for: .withoutResponse)
            connectionDiagnostics = "fff1 properties: \(characteristic.properties.displayDescription). Max write \(maxResponse)/\(maxNoResponse). Detected \(displayWidth)x\(displayHeight)."
            diagnostics = connectionDiagnostics
            if characteristic.properties.contains(.notify) || characteristic.properties.contains(.indicate) {
                waitingForNotificationSetup = true
                status = "Opening display response channel..."
                peripheral.setNotifyValue(true, for: characteristic)
                return
            }
            markConnected(to: peripheral)
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        Task { @MainActor in
            if let error {
                status = "Notification setup failed: \(error.localizedDescription)"
                notificationsEnabled = false
                waitingForNotificationSetup = false
                resumePending(.failure(error))
                return
            }
            notificationsEnabled = characteristic.isNotifying
            connectionDiagnostics = "\(connectionDiagnostics) Notify \(characteristic.isNotifying ? "enabled" : "off")."
            diagnostics = connectionDiagnostics
            if waitingForNotificationSetup {
                waitingForNotificationSetup = false
                if characteristic.isNotifying {
                    markConnected(to: peripheral)
                } else {
                    resumePending(.failure(CoolLedxBluetoothError.notificationsUnavailable))
                }
            }
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        Task { @MainActor in
            if let error {
                resumeWrite(.failure(error))
            } else {
                resumeWrite(.success(()))
            }
        }
    }

    nonisolated func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        Task { @MainActor in
            if let readContinuation {
                self.readContinuation = nil
                if let error {
                    diagnostics = "\(connectionDiagnostics)\nRead error: \(error.localizedDescription)"
                    readContinuation.resume(returning: nil)
                } else {
                    readContinuation.resume(returning: characteristic.value)
                }
                return
            }

            if let error {
                diagnostics = "\(connectionDiagnostics)\nNotify error: \(error.localizedDescription)"
            } else if let value = characteristic.value {
                diagnostics = "\(connectionDiagnostics)\nNotify from \(characteristic.uuid.uuidString): \(value.hexPrefix(maxBytes: 16))"
            }
            resumeNotify()
        }
    }
}

enum CoolLedxBluetoothError: LocalizedError {
    case notConnected
    case connectionFailed
    case noServices
    case noCoolLedCharacteristic
    case notificationsUnavailable
    case displayDidNotAcknowledge(chunkIndex: Int, totalChunks: Int)

    var errorDescription: String? {
        switch self {
        case .notConnected:
            return "No writable Bluetooth characteristic is connected."
        case .connectionFailed:
            return "The Bluetooth connection failed."
        case .noServices:
            return "The display did not expose Bluetooth services."
        case .noCoolLedCharacteristic:
            return "The CoolLED Bluetooth characteristic fff1 was not found."
        case .notificationsUnavailable:
            return "The display response channel was not available."
        case let .displayDidNotAcknowledge(chunkIndex, totalChunks):
            return "The display did not acknowledge image chunk \(chunkIndex) of \(totalChunks)."
        }
    }
}

private extension CBCharacteristicProperties {
    var displayDescription: String {
        var labels: [String] = []
        if contains(.read) { labels.append("read") }
        if contains(.write) { labels.append("write") }
        if contains(.writeWithoutResponse) { labels.append("writeWithoutResponse") }
        if contains(.notify) { labels.append("notify") }
        if contains(.indicate) { labels.append("indicate") }
        return labels.isEmpty ? "none" : labels.joined(separator: ", ")
    }
}

private extension Data {
    func hexPrefix(maxBytes: Int = 10) -> String {
        prefix(maxBytes).map { String(format: "%02x", $0) }.joined(separator: " ")
    }
}

enum CoolLedxPacketBuilder {
    static let characteristicUUID = "0000fff1-0000-1000-8000-00805f9b34fb"

    static func startDisplayCommandChunks() -> [Data] {
        [createCommand(rawData: Data([0x09, 0x01]))]
    }

    static func pictureModeCommandChunks() -> [Data] {
        [createCommand(rawData: Data([0x06, 0x07]))]
    }

    static func imageCommandChunks(pixelImage: PixelImage) -> [Data] {
        let imagePayload = makeImagePayload(pixelImage: pixelImage)
        return chopUpData(imagePayload, command: 0x03).map(createCommand)
    }

    private static func makeImagePayload(pixelImage: PixelImage) -> Data {
        var pixelBits = Data()

        for colorShift in [16, 8, 0] {
            for x in 0..<pixelImage.width {
                var packedByte: UInt8 = 0
                for y in 0..<pixelImage.height {
                    let value = pixelImage.rgbValues[y * pixelImage.width + x]
                    let component = (value >> colorShift) & 0xff
                    packedByte = (packedByte << 1) | (component >= 128 ? 1 : 0)
                    if y % 8 == 7 {
                        pixelBits.append(packedByte)
                        packedByte = 0
                    }
                }
            }
        }

        var payload = Data(repeating: 0, count: 24)
        payload.append(UInt8((pixelBits.count >> 8) & 0xff))
        payload.append(UInt8(pixelBits.count & 0xff))
        payload.append(pixelBits)
        return payload
    }

    private static func chopUpData(_ data: Data, command: UInt8) -> [Data] {
        stride(from: 0, to: data.count, by: 128).enumerated().map { chunkId, offset in
            let end = min(data.count, offset + 128)
            let rawChunk = data.subdata(in: offset..<end)
            var formatted = Data()
            formatted.append(0x00)
            formatted.append(UInt8((data.count >> 8) & 0xff))
            formatted.append(UInt8(data.count & 0xff))
            formatted.append(UInt8((chunkId >> 8) & 0xff))
            formatted.append(UInt8(chunkId & 0xff))
            formatted.append(UInt8(rawChunk.count))
            formatted.append(rawChunk)

            var checksum: UInt8 = 0
            for byte in formatted {
                checksum ^= byte
            }
            formatted.append(checksum)

            var chunk = Data([command])
            chunk.append(formatted)
            return chunk
        }
    }

    private static func createCommand(rawData: Data) -> Data {
        var extended = Data()
        extended.append(UInt8((rawData.count >> 8) & 0xff))
        extended.append(UInt8(rawData.count & 0xff))
        extended.append(rawData)

        var escaped = Data([0x01])
        for byte in extended {
            switch byte {
            case 0x01:
                escaped.append(contentsOf: [0x02, 0x05])
            case 0x02:
                escaped.append(contentsOf: [0x02, 0x06])
            case 0x03:
                escaped.append(contentsOf: [0x02, 0x07])
            default:
                escaped.append(byte)
            }
        }
        escaped.append(0x03)
        return escaped
    }
}
