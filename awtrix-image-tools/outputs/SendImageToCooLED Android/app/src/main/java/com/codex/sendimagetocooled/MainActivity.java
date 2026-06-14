package com.codex.sendimagetocooled;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final int PICK_IMAGE = 1001;
    private static final int REQUEST_BLUETOOTH = 1002;
    private static final int DISPLAY_WIDTH = 64;
    private static final int DISPLAY_HEIGHT = 16;
    private static final UUID COOLLEDX_CHARACTERISTIC = UUID.fromString("0000fff1-0000-1000-8000-00805f9b34fb");

    private BluetoothAdapter bluetoothAdapter;
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic writeCharacteristic;
    private final List<BluetoothDevice> devices = new ArrayList<>();
    private final Set<String> seenAddresses = new HashSet<>();
    private final List<byte[]> pendingChunks = new ArrayList<>();
    private int pendingChunkIndex;

    private LinearLayout deviceList;
    private Button scanButton;
    private Button pickButton;
    private Button uploadButton;
    private ProgressBar progressBar;
    private TextView statusView;
    private TextView connectedView;
    private PixelPreviewView previewView;
    private PixelImage pixelImage;
    private boolean scanning;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        BluetoothManager manager = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        bluetoothAdapter = manager == null ? null : manager.getAdapter();
        scanner = bluetoothAdapter == null ? null : bluetoothAdapter.getBluetoothLeScanner();
        setContentView(makeContentView());
        ensureBluetoothPermissions();
    }

    @Override
    protected void onDestroy() {
        stopScan();
        if (gatt != null) {
            gatt.close();
        }
        super.onDestroy();
    }

    private View makeContentView() {
        ScrollView scrollView = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(24));
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        scrollView.addView(root, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView title = new TextView(this);
        title.setText("SendImageToCooLED");
        title.setTextSize(26);
        title.setTextColor(Color.rgb(24, 35, 40));
        title.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        root.addView(title, matchWrap());

        connectedView = new TextView(this);
        connectedView.setText("No display connected");
        connectedView.setTextSize(16);
        connectedView.setTextColor(Color.rgb(68, 79, 86));
        root.addView(connectedView, withTopMargin(matchWrap(), 14));

        scanButton = new Button(this);
        scanButton.setText("Scan for CoolLEDX");
        scanButton.setAllCaps(false);
        scanButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (scanning) {
                    stopScan();
                } else {
                    startScan();
                }
            }
        });
        root.addView(scanButton, withTopMargin(matchWrap(), 12));

        deviceList = new LinearLayout(this);
        deviceList.setOrientation(LinearLayout.VERTICAL);
        root.addView(deviceList, withTopMargin(matchWrap(), 10));

        pickButton = new Button(this);
        pickButton.setText("Choose Image");
        pickButton.setAllCaps(false);
        pickButton.setEnabled(false);
        pickButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                pickImage();
            }
        });
        root.addView(pickButton, withTopMargin(matchWrap(), 18));

        previewView = new PixelPreviewView(this);
        root.addView(previewView, withTopMargin(matchWrap(), 18));

        uploadButton = new Button(this);
        uploadButton.setText("Upload to Display");
        uploadButton.setAllCaps(false);
        uploadButton.setEnabled(false);
        uploadButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                uploadImage();
            }
        });
        root.addView(uploadButton, withTopMargin(matchWrap(), 18));

        progressBar = new ProgressBar(this);
        progressBar.setVisibility(View.GONE);
        root.addView(progressBar, withTopMargin(wrapWrap(), 12));

        statusView = new TextView(this);
        statusView.setText("Scan for the display, then choose an image.");
        statusView.setTextSize(15);
        statusView.setTextColor(Color.rgb(84, 94, 100));
        root.addView(statusView, withTopMargin(matchWrap(), 12));

        return scrollView;
    }

    private void ensureBluetoothPermissions() {
        if (bluetoothAdapter == null) {
            statusView.setText("Bluetooth is not available on this device.");
            scanButton.setEnabled(false);
            return;
        }
        if (!bluetoothAdapter.isEnabled()) {
            statusView.setText("Turn on Bluetooth before scanning.");
        }
        if (Build.VERSION.SDK_INT >= 31) {
            List<String> missing = new ArrayList<>();
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
                missing.add(Manifest.permission.BLUETOOTH_SCAN);
            }
            if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                missing.add(Manifest.permission.BLUETOOTH_CONNECT);
            }
            if (!missing.isEmpty()) {
                requestPermissions(missing.toArray(new String[0]), REQUEST_BLUETOOTH);
            }
        } else if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] { Manifest.permission.ACCESS_FINE_LOCATION }, REQUEST_BLUETOOTH);
        }
    }

    private boolean hasBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
        }
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void startScan() {
        ensureBluetoothPermissions();
        if (!hasBluetoothPermissions()) {
            statusView.setText("Bluetooth permission is required.");
            return;
        }
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled()) {
            startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS));
            return;
        }
        scanner = bluetoothAdapter.getBluetoothLeScanner();
        if (scanner == null) {
            statusView.setText("Bluetooth scanner is not ready.");
            return;
        }

        devices.clear();
        seenAddresses.clear();
        deviceList.removeAllViews();
        scanning = true;
        scanButton.setText("Stop Scan");
        statusView.setText("Scanning for CoolLEDX displays...");
        scanner.startScan(scanCallback);
    }

    private void stopScan() {
        if (scanner != null && scanning && hasBluetoothPermissions()) {
            scanner.stopScan(scanCallback);
        }
        scanning = false;
        if (scanButton != null) {
            scanButton.setText("Scan for CoolLEDX");
        }
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            BluetoothDevice device = result.getDevice();
            String address = device.getAddress();
            if (seenAddresses.contains(address)) {
                return;
            }
            seenAddresses.add(address);
            devices.add(device);
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    addDeviceButton(device);
                }
            });
        }

        @Override
        public void onScanFailed(int errorCode) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    scanning = false;
                    scanButton.setText("Scan for CoolLEDX");
                    statusView.setText("Scan failed: " + errorCode);
                }
            });
        }
    };

    private void addDeviceButton(BluetoothDevice device) {
        Button button = new Button(this);
        String name = device.getName();
        button.setText((name == null || name.trim().isEmpty() ? "Unnamed display" : name) + "\n" + device.getAddress());
        button.setAllCaps(false);
        button.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                connectToDevice(device);
            }
        });
        deviceList.addView(button, withTopMargin(matchWrap(), 8));
    }

    private void connectToDevice(BluetoothDevice device) {
        stopScan();
        if (!hasBluetoothPermissions()) {
            statusView.setText("Bluetooth permission is required.");
            return;
        }
        setBusy(true, "Connecting to " + displayName(device) + "...");
        if (gatt != null) {
            gatt.close();
            gatt = null;
        }
        gatt = device.connectGatt(this, false, gattCallback);
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                gatt.discoverServices();
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        writeCharacteristic = null;
                        connectedView.setText("No display connected");
                        pickButton.setEnabled(false);
                        uploadButton.setEnabled(false);
                        setBusy(false, "Disconnected.");
                    }
                });
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            BluetoothGattCharacteristic found = null;
            for (BluetoothGattService service : gatt.getServices()) {
                BluetoothGattCharacteristic candidate = service.getCharacteristic(COOLLEDX_CHARACTERISTIC);
                if (candidate != null) {
                    found = candidate;
                    break;
                }
            }
            if (found == null) {
                for (BluetoothGattService service : gatt.getServices()) {
                    for (BluetoothGattCharacteristic candidate : service.getCharacteristics()) {
                        int props = candidate.getProperties();
                        if ((props & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0
                                || (props & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0) {
                            found = candidate;
                            break;
                        }
                    }
                    if (found != null) {
                        break;
                    }
                }
            }

            BluetoothGattCharacteristic finalFound = found;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (finalFound == null) {
                        setBusy(false, "No writable CoolLEDX characteristic found.");
                        return;
                    }
                    writeCharacteristic = finalFound;
                    connectedView.setText("Connected: " + displayName(gatt.getDevice()));
                    pickButton.setEnabled(true);
                    uploadButton.setEnabled(pixelImage != null);
                    setBusy(false, "Connected. Choose an image.");
                }
            });
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setBusy(false, "Upload failed: Bluetooth write error " + status);
                    }
                });
                return;
            }
            sendNextChunk();
        }
    };

    private void pickImage() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("image/*");
        startActivityForResult(intent, PICK_IMAGE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_IMAGE && resultCode == RESULT_OK && data != null && data.getData() != null) {
            loadImage(data.getData());
        }
    }

    private void loadImage(Uri uri) {
        setBusy(true, "Loading image...");
        new Thread(new Runnable() {
            @Override
            public void run() {
            try (InputStream input = new BufferedInputStream(getContentResolver().openInputStream(uri))) {
                Bitmap source = BitmapFactory.decodeStream(input);
                if (source == null) {
                    throw new IllegalArgumentException("Image could not be decoded.");
                }
                final PixelImage converted = makePixelImage(source);
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        pixelImage = converted;
                        previewView.setPixelImage(converted);
                        uploadButton.setEnabled(writeCharacteristic != null);
                        setBusy(false, "Ready: converted to 64x16.");
                    }
                });
            } catch (Exception e) {
                final String message = e.getMessage();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setBusy(false, "Image load failed: " + message);
                    }
                });
            }
            }
        }).start();
    }

    private PixelImage makePixelImage(Bitmap source) {
        float targetAspect = DISPLAY_WIDTH / (float) DISPLAY_HEIGHT;
        float imageAspect = source.getWidth() / (float) source.getHeight();
        int cropX = 0;
        int cropY = 0;
        int cropWidth = source.getWidth();
        int cropHeight = source.getHeight();
        if (imageAspect > targetAspect) {
            cropWidth = Math.round(source.getHeight() * targetAspect);
            cropX = (source.getWidth() - cropWidth) / 2;
        } else {
            cropHeight = Math.round(source.getWidth() / targetAspect);
            cropY = (source.getHeight() - cropHeight) / 2;
        }

        Bitmap cropped = Bitmap.createBitmap(source, cropX, cropY, cropWidth, cropHeight);
        Bitmap scaled = Bitmap.createScaledBitmap(cropped, DISPLAY_WIDTH, DISPLAY_HEIGHT, true);
        int[] values = new int[DISPLAY_WIDTH * DISPLAY_HEIGHT];
        scaled.getPixels(values, 0, DISPLAY_WIDTH, 0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT);

        int[] adjusted = new int[values.length];
        for (int i = 0; i < values.length; i++) {
            adjusted[i] = adjustColor(values[i]);
        }
        return new PixelImage(DISPLAY_WIDTH, DISPLAY_HEIGHT, adjusted);
    }

    private int adjustColor(int color) {
        double r = Color.red(color);
        double g = Color.green(color);
        double b = Color.blue(color);
        double luma = (0.299 * r) + (0.587 * g) + (0.114 * b);
        int rr = clamp(((luma + (r - luma) * 1.35) - 128) * 1.18 + 128);
        int gg = clamp(((luma + (g - luma) * 1.35) - 128) * 1.18 + 128);
        int bb = clamp(((luma + (b - luma) * 1.35) - 128) * 1.18 + 128);
        return Color.rgb(rr, gg, bb);
    }

    private int clamp(double value) {
        return Math.max(0, Math.min(255, (int) Math.round(value)));
    }

    private void uploadImage() {
        if (pixelImage == null || gatt == null || writeCharacteristic == null) {
            statusView.setText("Connect to the display and choose an image first.");
            return;
        }
        pendingChunks.clear();
        pendingChunks.addAll(CoolLedxProtocol.imageCommandChunks(pixelImage));
        pendingChunkIndex = 0;
        setBusy(true, String.format(Locale.US, "Uploading %d chunks...", pendingChunks.size()));
        sendNextChunk();
    }

    private void sendNextChunk() {
        if (pendingChunkIndex >= pendingChunks.size()) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    setBusy(false, "Uploaded to the CoolLEDX display.");
                }
            });
            return;
        }
        byte[] chunk = pendingChunks.get(pendingChunkIndex++);
        writeCharacteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
        writeCharacteristic.setValue(chunk);
        boolean started = gatt.writeCharacteristic(writeCharacteristic);
        if (!started) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    setBusy(false, "Upload failed: Bluetooth write did not start.");
                }
            });
        }
    }

    private void setBusy(boolean busy, String status) {
        progressBar.setVisibility(busy ? View.VISIBLE : View.GONE);
        scanButton.setEnabled(!busy);
        pickButton.setEnabled(!busy && writeCharacteristic != null);
        uploadButton.setEnabled(!busy && writeCharacteristic != null && pixelImage != null);
        statusView.setText(status);
    }

    private String displayName(BluetoothDevice device) {
        String name = device.getName();
        return name == null || name.trim().isEmpty() ? device.getAddress() : name;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams wrapWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams withTopMargin(LinearLayout.LayoutParams params, int marginDp) {
        params.topMargin = dp(marginDp);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class PixelImage {
        final int width;
        final int height;
        final int[] pixels;

        PixelImage(int width, int height, int[] pixels) {
            this.width = width;
            this.height = height;
            this.pixels = pixels;
        }
    }

    private static final class PixelPreviewView extends View {
        private final Paint paint = new Paint();
        private PixelImage image;

        PixelPreviewView(Context context) {
            super(context);
            setMinimumHeight(120);
        }

        void setPixelImage(PixelImage image) {
            this.image = image;
            invalidate();
        }

        @Override
        protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
            int width = MeasureSpec.getSize(widthMeasureSpec);
            int height = Math.max(80, Math.round(width / 4f));
            setMeasuredDimension(width, height);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            canvas.drawColor(Color.BLACK);
            if (image == null) {
                return;
            }
            float cell = Math.min(getWidth() / (float) image.width, getHeight() / (float) image.height);
            float left = (getWidth() - cell * image.width) / 2f;
            float top = (getHeight() - cell * image.height) / 2f;
            for (int y = 0; y < image.height; y++) {
                for (int x = 0; x < image.width; x++) {
                    paint.setColor(image.pixels[y * image.width + x]);
                    canvas.drawRect(left + x * cell, top + y * cell, left + (x + 1) * cell, top + (y + 1) * cell, paint);
                }
            }
        }
    }

    private static final class CoolLedxProtocol {
        static List<byte[]> imageCommandChunks(PixelImage image) {
            byte[] payload = makeImagePayload(image);
            List<byte[]> chunks = new ArrayList<>();
            int chunkId = 0;
            for (int offset = 0; offset < payload.length; offset += 128) {
                int size = Math.min(128, payload.length - offset);
                ByteArrayOutputStream formatted = new ByteArrayOutputStream();
                formatted.write(0x00);
                formatted.write((payload.length >> 8) & 0xff);
                formatted.write(payload.length & 0xff);
                formatted.write((chunkId >> 8) & 0xff);
                formatted.write(chunkId & 0xff);
                formatted.write(size);
                formatted.write(payload, offset, size);
                byte checksum = 0;
                byte[] formattedBytes = formatted.toByteArray();
                for (byte value : formattedBytes) {
                    checksum = (byte) (checksum ^ value);
                }
                formatted.write(checksum & 0xff);

                ByteArrayOutputStream raw = new ByteArrayOutputStream();
                raw.write(0x03);
                byte[] completeFormatted = formatted.toByteArray();
                raw.write(completeFormatted, 0, completeFormatted.length);
                chunks.add(createCommand(raw.toByteArray()));
                chunkId++;
            }
            return chunks;
        }

        private static byte[] makeImagePayload(PixelImage image) {
            ByteArrayOutputStream bits = new ByteArrayOutputStream();
            int[] shifts = new int[] {16, 8, 0};
            for (int shift : shifts) {
                for (int x = 0; x < image.width; x++) {
                    int packed = 0;
                    for (int y = 0; y < image.height; y++) {
                        int component = (image.pixels[y * image.width + x] >> shift) & 0xff;
                        packed = (packed << 1) | (component >= 128 ? 1 : 0);
                        if (y % 8 == 7) {
                            bits.write(packed & 0xff);
                            packed = 0;
                        }
                    }
                }
            }

            byte[] pixelBits = bits.toByteArray();
            ByteArrayOutputStream payload = new ByteArrayOutputStream();
            for (int i = 0; i < 24; i++) {
                payload.write(0x00);
            }
            payload.write((pixelBits.length >> 8) & 0xff);
            payload.write(pixelBits.length & 0xff);
            payload.write(pixelBits, 0, pixelBits.length);
            return payload.toByteArray();
        }

        private static byte[] createCommand(byte[] raw) {
            ByteArrayOutputStream extended = new ByteArrayOutputStream();
            extended.write((raw.length >> 8) & 0xff);
            extended.write(raw.length & 0xff);
            extended.write(raw, 0, raw.length);

            ByteArrayOutputStream escaped = new ByteArrayOutputStream();
            escaped.write(0x01);
            for (byte byteValue : extended.toByteArray()) {
                int value = byteValue & 0xff;
                if (value == 0x01) {
                    escaped.write(0x02);
                    escaped.write(0x05);
                } else if (value == 0x02) {
                    escaped.write(0x02);
                    escaped.write(0x06);
                } else if (value == 0x03) {
                    escaped.write(0x02);
                    escaped.write(0x07);
                } else {
                    escaped.write(value);
                }
            }
            escaped.write(0x03);
            return escaped.toByteArray();
        }
    }
}
