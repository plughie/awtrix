package com.codex.sendimagetoawtrix;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class MainActivity extends Activity {
    private static final int PICK_IMAGE = 1001;
    private static final int PIXEL_SIZE = 32;
    private static final int FRAME_WIDTH = 32;
    private static final int FRAME_HEIGHT = 8;
    private static final int BAR_SIZE = 4;
    private static final String APP_PREFIX = "image_to_awtrix";
    private static final String DIRECTION_TOP_TO_BOTTOM = "top_to_bottom";
    private static final String DIRECTION_BOTTOM_TO_TOP = "bottom_to_top";
    private static final String DIRECTION_LEFT_TO_RIGHT = "left_to_right";
    private static final String DIRECTION_RIGHT_TO_LEFT = "right_to_left";
    private static final double SATURATION = 1.35;
    private static final double CONTRAST = 1.18;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText hostField;
    private EditText secondsField;
    private Button pickButton;
    private Button connectButton;
    private Button sendButton;
    private Button convertCropButton;
    private CheckBox loopCheckBox;
    private CheckBox keepRotationCheckBox;
    private RadioGroup directionGroup;
    private ProgressBar progressBar;
    private TextView statusView;
    private ImageCropView cropView;
    private PixelPreviewView previewView;
    private Bitmap sourceBitmap;
    private PixelImage pixelImage;
    private SharedPreferences prefs;
    private Future<?> sendFuture;
    private volatile boolean isSending;
    private volatile boolean isConnected;
    private volatile boolean isCheckingConnection;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("settings", MODE_PRIVATE);
        setContentView(makeContentView());
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private View makeContentView() {
        ScrollView scrollView = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(22));
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        scrollView.addView(root, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView title = new TextView(this);
        title.setText("Send Image to AWTRIX");
        title.setTextSize(26);
        title.setTextColor(Color.rgb(24, 35, 40));
        title.setGravity(Gravity.START);
        title.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        root.addView(title, matchWrap());

        cropView = new ImageCropView(this);
        cropView.setVisibility(View.GONE);
        LinearLayout.LayoutParams cropParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        cropParams.topMargin = dp(18);
        root.addView(cropView, cropParams);

        convertCropButton = new Button(this);
        convertCropButton.setText("Convert Crop");
        convertCropButton.setAllCaps(false);
        convertCropButton.setVisibility(View.GONE);
        convertCropButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                convertCrop();
            }
        });
        root.addView(convertCropButton, withTopMargin(matchWrap(), 12));

        previewView = new PixelPreviewView(this);
        LinearLayout.LayoutParams previewParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        previewParams.topMargin = dp(18);
        root.addView(previewView, previewParams);

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

        TextView ipLabel = label("AWTRIX IP Address");
        root.addView(ipLabel, withTopMargin(matchWrap(), 18));

        hostField = new EditText(this);
        hostField.setSingleLine(true);
        hostField.setHint("192.168.1.50");
        hostField.setInputType(android.text.InputType.TYPE_CLASS_TEXT);
        hostField.setText(prefs.getString("host", ""));
        hostField.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                isConnected = false;
                sourceBitmap = null;
                pixelImage = null;
                previewView.setPixelImage(null);
                cropView.setVisibility(View.GONE);
                convertCropButton.setVisibility(View.GONE);
                updateActionControls();
                statusView.setText("Connect to AWTRIX before choosing an image.");
            }

            @Override
            public void afterTextChanged(Editable s) {
            }
        });
        root.addView(hostField, matchWrap());

        connectButton = new Button(this);
        connectButton.setText("Connect");
        connectButton.setAllCaps(false);
        connectButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                connectToAwtrix();
            }
        });
        root.addView(connectButton, withTopMargin(matchWrap(), 12));

        loopCheckBox = new CheckBox(this);
        loopCheckBox.setText("Loop until stopped");
        loopCheckBox.setTextSize(16);
        loopCheckBox.setTextColor(Color.rgb(24, 35, 40));
        root.addView(loopCheckBox, withTopMargin(matchWrap(), 12));

        keepRotationCheckBox = new CheckBox(this);
        keepRotationCheckBox.setText("Keep in app rotation");
        keepRotationCheckBox.setTextSize(16);
        keepRotationCheckBox.setTextColor(Color.rgb(24, 35, 40));
        root.addView(keepRotationCheckBox, withTopMargin(matchWrap(), 8));

        TextView secondsLabel = label("Cycle Seconds");
        root.addView(secondsLabel, withTopMargin(matchWrap(), 12));

        secondsField = new EditText(this);
        secondsField.setSingleLine(true);
        secondsField.setHint("8");
        secondsField.setInputType(android.text.InputType.TYPE_CLASS_NUMBER | android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        secondsField.setText(prefs.getString("cycleSeconds", "8"));
        root.addView(secondsField, matchWrap());

        TextView directionLabel = label("Direction");
        root.addView(directionLabel, withTopMargin(matchWrap(), 12));

        directionGroup = new RadioGroup(this);
        directionGroup.setOrientation(RadioGroup.VERTICAL);
        addDirectionButton(directionGroup, DIRECTION_TOP_TO_BOTTOM, "Top to Bottom");
        addDirectionButton(directionGroup, DIRECTION_BOTTOM_TO_TOP, "Bottom to Top");
        addDirectionButton(directionGroup, DIRECTION_LEFT_TO_RIGHT, "Left to Right");
        addDirectionButton(directionGroup, DIRECTION_RIGHT_TO_LEFT, "Right to Left");
        selectDirection(prefs.getString("scrollDirection", DIRECTION_TOP_TO_BOTTOM));
        root.addView(directionGroup, matchWrap());

        sendButton = new Button(this);
        sendButton.setText("Upload and Run");
        sendButton.setAllCaps(false);
        sendButton.setEnabled(false);
        sendButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (isSending) {
                    stopAnimation();
                } else {
                    sendImage();
                }
            }
        });
        root.addView(sendButton, withTopMargin(matchWrap(), 18));

        progressBar = new ProgressBar(this);
        progressBar.setVisibility(View.GONE);
        root.addView(progressBar, withTopMargin(wrapWrap(), 12));

        statusView = new TextView(this);
        statusView.setText("Connect to AWTRIX before choosing an image.");
        statusView.setTextSize(15);
        statusView.setTextColor(Color.rgb(84, 94, 100));
        root.addView(statusView, withTopMargin(matchWrap(), 12));

        return scrollView;
    }

    private void addDirectionButton(RadioGroup group, String value, String label) {
        RadioButton button = new RadioButton(this);
        button.setId(View.generateViewId());
        button.setText(label);
        button.setTextSize(15);
        button.setTextColor(Color.rgb(24, 35, 40));
        button.setTag(value);
        group.addView(button, wrapWrap());
    }

    private TextView label(String text) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextSize(16);
        label.setTextColor(Color.rgb(24, 35, 40));
        label.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        return label;
    }

    private void connectToAwtrix() {
        final String host = normalizeHost(hostField.getText().toString().trim());
        if (host.isEmpty()) {
            statusView.setText("Enter the AWTRIX IP address.");
            return;
        }

        prefs.edit().putString("host", host).apply();
        hostField.setText(host);
        final boolean keepInRotation = keepRotationCheckBox != null && keepRotationCheckBox.isChecked();
        isCheckingConnection = true;
        progressBar.setVisibility(View.VISIBLE);
        statusView.setText("Checking AWTRIX connection...");
        updateActionControls();
        executor.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    prepareForUpload(host, APP_PREFIX, keepInRotation);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            isConnected = true;
                            isCheckingConnection = false;
                            progressBar.setVisibility(View.GONE);
                            statusView.setText("Connected. Choose an image.");
                            updateActionControls();
                        }
                    });
                } catch (Exception e) {
                    final String message = e.getMessage();
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            isConnected = false;
                            isCheckingConnection = false;
                            progressBar.setVisibility(View.GONE);
                            statusView.setText("Connection failed: " + message);
                            updateActionControls();
                        }
                    });
                }
            }
        });
    }

    private void pickImage() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("image/*");
        startActivityForResult(intent, PICK_IMAGE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_IMAGE || resultCode != RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        loadImage(data.getData());
    }

    private void loadImage(Uri uri) {
        setBusy(true, "Loading image...");
        executor.execute(new Runnable() {
            @Override
            public void run() {
            try (InputStream input = new BufferedInputStream(getContentResolver().openInputStream(uri))) {
                Bitmap source = BitmapFactory.decodeStream(input);
                if (source == null) {
                    throw new IllegalArgumentException("Image could not be decoded.");
                }
                final Bitmap loaded = source;
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                    sourceBitmap = loaded;
                    pixelImage = null;
                    previewView.setPixelImage(null);
                    cropView.setBitmap(loaded);
                    cropView.setVisibility(View.VISIBLE);
                    convertCropButton.setVisibility(View.VISIBLE);
                    sendButton.setEnabled(false);
                    setBusy(false, "Adjust the crop rectangle, then convert it.");
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
        });
    }

    private void convertCrop() {
        if (sourceBitmap == null) {
            return;
        }
        Rect crop = cropView.getCropRect();
        pixelImage = makePixelImage(sourceBitmap, crop);
        previewView.setPixelImage(pixelImage);
        sendButton.setEnabled(!hostField.getText().toString().trim().isEmpty());
        statusView.setText("Ready: selected crop converted to 32x" + pixelImage.height + ".");
    }

    private PixelImage makePixelImage(Bitmap source, Rect crop) {
        Bitmap cropped = Bitmap.createBitmap(source, crop.left, crop.top, crop.width(), crop.height());
        int scaledHeight = Math.max(FRAME_HEIGHT, Math.round(crop.height() / (float) crop.width() * PIXEL_SIZE));
        Bitmap scaled = Bitmap.createScaledBitmap(cropped, PIXEL_SIZE, scaledHeight, true);
        int[] values = new int[PIXEL_SIZE * scaledHeight];
        scaled.getPixels(values, 0, PIXEL_SIZE, 0, 0, PIXEL_SIZE, scaledHeight);

        int[] adjusted = new int[values.length];
        for (int i = 0; i < values.length; i++) {
            adjusted[i] = adjustColor(values[i]);
        }
        return new PixelImage(PIXEL_SIZE, scaledHeight, adjusted);
    }

    private int adjustColor(int color) {
        double r = Color.red(color);
        double g = Color.green(color);
        double b = Color.blue(color);
        double luma = (0.299 * r) + (0.587 * g) + (0.114 * b);
        int rr = clamp(((luma + (r - luma) * SATURATION) - 128) * CONTRAST + 128);
        int gg = clamp(((luma + (g - luma) * SATURATION) - 128) * CONTRAST + 128);
        int bb = clamp(((luma + (b - luma) * SATURATION) - 128) * CONTRAST + 128);
        return Color.rgb(rr, gg, bb);
    }

    private int clamp(double value) {
        return Math.max(0, Math.min(255, (int) Math.round(value)));
    }

    private void sendImage() {
        if (pixelImage == null) {
            return;
        }
        String host = hostField.getText().toString().trim();
        if (host.isEmpty()) {
            statusView.setText("Enter the AWTRIX IP address.");
            return;
        }
        if (!isConnected) {
            statusView.setText("Connect to AWTRIX first.");
            return;
        }

        String finalAppPrefix = APP_PREFIX;
        boolean shouldLoop = loopCheckBox.isChecked();
        boolean keepInRotation = keepRotationCheckBox != null && keepRotationCheckBox.isChecked();
        double cycleSeconds = getCycleSeconds();
        String direction = getDirection();
        prefs.edit()
                .putString("host", host)
                .putString("cycleSeconds", secondsField.getText().toString().trim())
                .putString("scrollDirection", direction)
                .apply();
        setBusy(true, "Sending one-shot AWTRIX frames...");
        loopCheckBox.setEnabled(false);
        secondsField.setEnabled(false);
        sendFuture = executor.submit(new Runnable() {
            @Override
            public void run() {
            try {
                send(host, finalAppPrefix, pixelImage, shouldLoop, cycleSeconds, direction, keepInRotation);
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setBusy(false, keepInRotation ? "Sent and kept in AWTRIX rotation." : "Sent and cleared from AWTRIX rotation.");
                    }
                });
            } catch (InterruptedException e) {
                try {
                    stop(host, finalAppPrefix, keepInRotation);
                } catch (Exception ignored) {
                }
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setBusy(false, "Animation stopped.");
                    }
                });
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                final String message = e.getMessage();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setBusy(false, "Send failed: " + message);
                    }
                });
            }
            }
        });
    }

    private void stopAnimation() {
        if (sendFuture != null) {
            sendFuture.cancel(true);
        }
        final String host = hostField.getText().toString().trim();
        final String finalAppPrefix = APP_PREFIX;
        final boolean keepInRotation = keepRotationCheckBox != null && keepRotationCheckBox.isChecked();
        setBusy(true, "Stopping animation...");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    stop(host, finalAppPrefix, keepInRotation);
                } catch (Exception ignored) {
                }
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        setBusy(false, "Animation stopped.");
                    }
                });
            }
        }).start();
    }

    private void prepareForUpload(String host, String appPrefix, boolean keepInRotation) throws Exception {
        getStatsWithRetry(host);
        if (!keepInRotation) {
            cleanupCustomApps(host, appPrefix);
        }
        getStatsWithRetry(host);
    }

    private void getStatsWithRetry(String host) throws Exception {
        try {
            get(host, "/api/stats");
        } catch (Exception e) {
            Thread.sleep(350);
            get(host, "/api/stats");
        }
    }

    private double getCycleSeconds() {
        try {
            double value = Double.parseDouble(secondsField.getText().toString().trim());
            return Math.max(1.0, Math.min(120.0, value));
        } catch (Exception e) {
            return 8.0;
        }
    }

    private String getDirection() {
        if (directionGroup == null) {
            return DIRECTION_TOP_TO_BOTTOM;
        }
        RadioButton selected = findViewById(directionGroup.getCheckedRadioButtonId());
        Object tag = selected == null ? null : selected.getTag();
        return tag instanceof String ? (String) tag : DIRECTION_TOP_TO_BOTTOM;
    }

    private void selectDirection(String direction) {
        if (directionGroup == null) {
            return;
        }
        for (int index = 0; index < directionGroup.getChildCount(); index++) {
            View child = directionGroup.getChildAt(index);
            if (direction.equals(child.getTag())) {
                directionGroup.check(child.getId());
                return;
            }
        }
        if (directionGroup.getChildCount() > 0) {
            directionGroup.check(directionGroup.getChildAt(0).getId());
        }
    }

    private void send(String host, String appPrefix, PixelImage image, boolean loop, double totalSeconds, String direction, boolean keepInRotation) throws Exception {
        getStatsWithRetry(host);
        List<int[]> frames = makeFrames(image, direction);
        long delayMillis = Math.round((totalSeconds / frames.size()) * 1000.0);
        int appDuration = loop ? 86400 : Math.max(1, (int) Math.ceil(totalSeconds) + 1);
        int appLifetime = keepInRotation ? 0 : appDuration + 2;

        postFrame(host, appPrefix, frames.get(0), appDuration, appLifetime, keepInRotation);
        JSONObject body = new JSONObject();
        body.put("name", appPrefix);
        post(host, "/api/switch", body.toString());

        do {
            for (int[] frame : frames) {
                if (Thread.currentThread().isInterrupted()) {
                    throw new InterruptedException();
                }
                postFrame(host, appPrefix, frame, appDuration, appLifetime, keepInRotation);
                Thread.sleep(delayMillis);
            }
        } while (loop);

        stop(host, appPrefix, keepInRotation);
    }

    private void stop(String host, String appPrefix, boolean keepInRotation) throws Exception {
        if (keepInRotation) {
            post(host, "/api/nextapp", null);
        } else {
            cleanupCustomApps(host, appPrefix);
        }
    }

    private void postFrame(String host, String appPrefix, int[] frame, int duration, int lifetime, boolean save) throws Exception {
        JSONObject payload = new JSONObject();
        JSONArray draw = new JSONArray();
        JSONArray db = new JSONArray();
        db.put(0);
        db.put(0);
        db.put(FRAME_WIDTH);
        db.put(FRAME_HEIGHT);
        JSONArray pixels = new JSONArray();
        for (int value : frame) {
            pixels.put(value & 0x00FFFFFF);
        }
        db.put(pixels);
        JSONObject drawCommand = new JSONObject();
        drawCommand.put("db", db);
        draw.put(drawCommand);
        payload.put("draw", draw);
        payload.put("duration", duration);
        payload.put("lifetime", lifetime);
        payload.put("noScroll", true);
        payload.put("save", save);
        post(host, "/api/custom?name=" + encode(appPrefix), payload.toString());
    }

    private void cleanupCustomApps(String host, String appPrefix) throws Exception {
        String[] names = new String[] {
                appPrefix,
                "image_to_awtrix_bar",
                "image_to_awtrix_bar_1",
                "image_to_awtrix_bar_2",
                "image_to_awtrix_bar_3",
                "image_to_awtrix_bar_4",
                "image_to_awtrix_bar_5",
                "image_to_awtrix_bar_6",
                "image_to_awtrix_bar_7",
                "image_to_awtrix_bar_8",
                "sacred_square",
                "sacred_square_1",
                "sacred_square_2",
                "sacred_square_3",
                "sacred_square_4",
                "sacred_square_bar",
                "sacred_square_bar_1",
                "sacred_square_bar_2",
                "sacred_square_bar_3",
                "sacred_square_bar_4",
                "sacred_square_bar_5",
                "sacred_square_bar_6",
                "sacred_square_bar_7",
                "sacred_square_bar_8",
                "_1",
                "_2",
                "_3",
                "_4",
                "_5",
                "_6",
                "_7",
                "_8"
        };

        for (int attempt = 0; attempt < 4; attempt++) {
            post(host, "/api/nextapp", null);
            Thread.sleep(800);

            for (String name : names) {
                post(host, "/api/custom?name=" + encode(name), null);
            }

            Thread.sleep(800);
            if (loopIsClean(host, names)) {
                return;
            }
        }

        throw new IllegalStateException("Temporary AWTRIX app is still in rotation.");
    }

    private boolean loopIsClean(String host, String[] names) throws Exception {
        String loop = get(host, "/api/loop");
        JSONObject object = new JSONObject(loop);
        for (String name : names) {
            if (object.has(name)) {
                return false;
            }
        }
        return true;
    }

    private List<int[]> makeFrames(PixelImage image, String direction) {
        if (DIRECTION_LEFT_TO_RIGHT.equals(direction) || DIRECTION_RIGHT_TO_LEFT.equals(direction)) {
            return makeHorizontalFrames(image, direction);
        }
        return makeVerticalFrames(image, direction);
    }

    private List<int[]> makeVerticalFrames(PixelImage image, String direction) {
        int frameCount = Math.max(1, (int) Math.ceil(image.height / (double) BAR_SIZE));
        List<int[]> frames = new ArrayList<>();
        for (int index = 0; index < frameCount; index++) {
            int frameIndex = DIRECTION_BOTTOM_TO_TOP.equals(direction) ? frameCount - 1 - index : index;
            int y = frameIndex * BAR_SIZE;
            frames.add(rows(image, y, FRAME_HEIGHT));
        }
        return frames;
    }

    private List<int[]> makeHorizontalFrames(PixelImage image, String direction) {
        int frameCount = Math.max(1, (int) Math.ceil(image.width / (double) BAR_SIZE));
        List<int[]> frames = new ArrayList<>();
        for (int index = 0; index < frameCount; index++) {
            int frameIndex = DIRECTION_RIGHT_TO_LEFT.equals(direction) ? frameCount - 1 - index : index;
            int x = frameIndex * BAR_SIZE;
            frames.add(columns(image, x, FRAME_WIDTH, FRAME_HEIGHT));
        }
        return frames;
    }

    private int[] rows(PixelImage image, int y, int height) {
        int[] values = new int[image.width * height];
        int out = 0;
        for (int row = y; row < y + height; row++) {
            if (row < 0 || row >= image.height) {
                for (int column = 0; column < image.width; column++) {
                    values[out++] = 0;
                }
                continue;
            }
            int start = row * image.width;
            for (int column = 0; column < image.width; column++) {
                values[out++] = image.pixels[start + column];
            }
        }
        return values;
    }

    private int[] columns(PixelImage image, int x, int width, int height) {
        int[] values = new int[width * height];
        int out = 0;
        for (int row = 0; row < height; row++) {
            for (int column = x; column < x + width; column++) {
                if (row < 0 || row >= image.height || column < 0 || column >= image.width) {
                    values[out++] = 0;
                } else {
                    values[out++] = image.pixels[row * image.width + column];
                }
            }
        }
        return values;
    }


    private String encode(String value) throws Exception {
        return URLEncoder.encode(value, StandardCharsets.UTF_8.name()).replace("+", "%20");
    }

    private String get(String host, String path) throws Exception {
        URL url = new URL("http://" + normalizeHost(host) + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("Connection", "close");
        int code = connection.getResponseCode();
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (InputStream input = code >= 400 ? connection.getErrorStream() : connection.getInputStream()) {
            if (input != null) {
                byte[] buffer = new byte[256];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    sink.write(buffer, 0, read);
                }
            }
        }
        connection.disconnect();
        if (code < 200 || code >= 300) {
            throw new IllegalStateException(String.format(Locale.US, "HTTP %d", code));
        }
        return sink.toString("UTF-8");
    }

    private void post(String host, String path, String body) throws Exception {
        URL url = new URL("http://" + normalizeHost(host) + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(10000);
        connection.setRequestMethod("POST");
        connection.setRequestProperty("Connection", "close");
        if (body != null) {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = new BufferedOutputStream(connection.getOutputStream())) {
                output.write(bytes);
            }
        }
        int code = connection.getResponseCode();
        try (InputStream ignored = code >= 400 ? connection.getErrorStream() : connection.getInputStream()) {
            if (ignored != null) {
                ByteArrayOutputStream sink = new ByteArrayOutputStream();
                byte[] buffer = new byte[256];
                int read;
                while ((read = ignored.read(buffer)) != -1) {
                    sink.write(buffer, 0, read);
                }
            }
        }
        connection.disconnect();
        if (code < 200 || code >= 300) {
            throw new IllegalStateException(String.format(Locale.US, "HTTP %d", code));
        }
    }

    private String normalizeHost(String value) {
        String host = value == null ? "" : value.trim();
        if (host.startsWith("http://")) {
            host = host.substring(7);
        } else if (host.startsWith("https://")) {
            host = host.substring(8);
        }
        int slash = host.indexOf('/');
        if (slash >= 0) {
            host = host.substring(0, slash);
        }
        int colon = host.indexOf(':');
        if (colon >= 0 && host.indexOf(':', colon + 1) < 0) {
            host = host.substring(0, colon);
        }
        return host.trim();
    }

    private void setBusy(boolean busy, String status) {
        isSending = busy;
        progressBar.setVisibility(busy ? View.VISIBLE : View.GONE);
        sendButton.setText(busy ? "Stop Animation" : "Upload and Run");
        sendButton.setEnabled((busy || pixelImage != null) && !hostField.getText().toString().trim().isEmpty());
        if (loopCheckBox != null) {
            loopCheckBox.setEnabled(!busy);
        }
        if (keepRotationCheckBox != null) {
            keepRotationCheckBox.setEnabled(!busy);
        }
        if (secondsField != null) {
            secondsField.setEnabled(!busy);
        }
        if (directionGroup != null) {
            directionGroup.setEnabled(!busy);
            for (int index = 0; index < directionGroup.getChildCount(); index++) {
                directionGroup.getChildAt(index).setEnabled(!busy);
            }
        }
        statusView.setText(status);
        updateActionControls();
    }

    private void updateActionControls() {
        boolean hasHost = !hostField.getText().toString().trim().isEmpty();
        if (connectButton != null) {
            connectButton.setEnabled(!isSending && !isCheckingConnection && hasHost);
            connectButton.setText(isCheckingConnection ? "Checking..." : (isConnected ? "Connected" : "Connect"));
        }
        if (pickButton != null) {
            pickButton.setEnabled(!isSending && !isCheckingConnection && isConnected);
        }
        if (convertCropButton != null) {
            convertCropButton.setEnabled(!isSending && !isCheckingConnection && isConnected);
        }
        if (sendButton != null) {
            sendButton.setEnabled((isSending || (!isCheckingConnection && isConnected && pixelImage != null)) && hasHost);
        }
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams wrapWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams withTopMargin(LinearLayout.LayoutParams params, int marginDp) {
        params.topMargin = dp(marginDp);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static class PixelImage {
        final int width;
        final int height;
        final int[] pixels;

        PixelImage(int width, int height, int[] pixels) {
            this.width = width;
            this.height = height;
            this.pixels = pixels;
        }
    }

    private static class ImageCropView extends View {
        private static final int MODE_NONE = 0;
        private static final int MODE_MOVE = 1;
        private static final int MODE_RESIZE = 2;

        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private Bitmap bitmap;
        private RectF imageRect = new RectF();
        private RectF cropRect = new RectF();
        private int mode = MODE_NONE;
        private float lastX;
        private float lastY;
        private float resizeAnchorX;
        private float resizeAnchorY;
        private float minCropSize;

        ImageCropView(Context context) {
            super(context);
            setBackgroundColor(Color.rgb(16, 18, 20));
        }

        void setBitmap(Bitmap bitmap) {
            this.bitmap = bitmap;
            resetCrop();
            requestLayout();
            invalidate();
        }

        Rect getCropRect() {
            if (bitmap == null || imageRect.width() <= 0 || cropRect.width() <= 0) {
                return new Rect(0, 0, 1, 1);
            }
            float scaleX = bitmap.getWidth() / imageRect.width();
            float scaleY = bitmap.getHeight() / imageRect.height();
            int left = clampInt(Math.round((cropRect.left - imageRect.left) * scaleX), 0, bitmap.getWidth() - 1);
            int top = clampInt(Math.round((cropRect.top - imageRect.top) * scaleY), 0, bitmap.getHeight() - 1);
            int width = clampInt(Math.round(cropRect.width() * scaleX), 1, bitmap.getWidth() - left);
            int height = clampInt(Math.round(cropRect.height() * scaleY), 1, bitmap.getHeight() - top);
            return new Rect(left, top, left + width, top + height);
        }

        @Override
        protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
            int width = MeasureSpec.getSize(widthMeasureSpec);
            int height = Math.max(1, Math.round(width * 0.85f));
            setMeasuredDimension(width, height);
        }

        @Override
        protected void onSizeChanged(int w, int h, int oldw, int oldh) {
            layoutImageRect(w, h);
            resetCrop();
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            if (bitmap == null) {
                paint.setColor(Color.rgb(38, 42, 46));
                canvas.drawRect(0, 0, getWidth(), getHeight(), paint);
                return;
            }

            canvas.drawBitmap(bitmap, null, imageRect, paint);

            paint.setColor(Color.argb(150, 0, 0, 0));
            canvas.drawRect(imageRect.left, imageRect.top, imageRect.right, cropRect.top, paint);
            canvas.drawRect(imageRect.left, cropRect.bottom, imageRect.right, imageRect.bottom, paint);
            canvas.drawRect(imageRect.left, cropRect.top, cropRect.left, cropRect.bottom, paint);
            canvas.drawRect(cropRect.right, cropRect.top, imageRect.right, cropRect.bottom, paint);

            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(3f);
            paint.setColor(Color.WHITE);
            canvas.drawRect(cropRect, paint);

            paint.setStrokeWidth(1.5f);
            paint.setColor(Color.argb(210, 255, 255, 255));
            float xThird = cropRect.width() / 3f;
            float yThird = cropRect.height() / 3f;
            canvas.drawLine(cropRect.left + xThird, cropRect.top, cropRect.left + xThird, cropRect.bottom, paint);
            canvas.drawLine(cropRect.left + xThird * 2f, cropRect.top, cropRect.left + xThird * 2f, cropRect.bottom, paint);
            canvas.drawLine(cropRect.left, cropRect.top + yThird, cropRect.right, cropRect.top + yThird, paint);
            canvas.drawLine(cropRect.left, cropRect.top + yThird * 2f, cropRect.right, cropRect.top + yThird * 2f, paint);

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.WHITE);
            float handle = 10f;
            canvas.drawCircle(cropRect.left, cropRect.top, handle, paint);
            canvas.drawCircle(cropRect.right, cropRect.top, handle, paint);
            canvas.drawCircle(cropRect.left, cropRect.bottom, handle, paint);
            canvas.drawCircle(cropRect.right, cropRect.bottom, handle, paint);
            paint.setStyle(Paint.Style.FILL);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            if (bitmap == null || imageRect.width() <= 0) {
                return false;
            }
            float x = event.getX();
            float y = event.getY();
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    lastX = x;
                    lastY = y;
                    if (nearCorner(x, y)) {
                        mode = MODE_RESIZE;
                        resizeAnchorX = x < cropRect.centerX() ? cropRect.right : cropRect.left;
                        resizeAnchorY = y < cropRect.centerY() ? cropRect.bottom : cropRect.top;
                    } else if (cropRect.contains(x, y)) {
                        mode = MODE_MOVE;
                    } else {
                        mode = MODE_NONE;
                    }
                    return true;
                case MotionEvent.ACTION_MOVE:
                    if (mode == MODE_MOVE) {
                        moveCrop(x - lastX, y - lastY);
                    } else if (mode == MODE_RESIZE) {
                        resizeCrop(x, y);
                    }
                    lastX = x;
                    lastY = y;
                    invalidate();
                    return true;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    mode = MODE_NONE;
                    return true;
                default:
                    return super.onTouchEvent(event);
            }
        }

        private void layoutImageRect(int width, int height) {
            if (bitmap == null || width <= 0 || height <= 0) {
                imageRect.set(0, 0, width, height);
                return;
            }
            float viewRatio = width / (float) height;
            float imageRatio = bitmap.getWidth() / (float) bitmap.getHeight();
            if (imageRatio > viewRatio) {
                float imageHeight = width / imageRatio;
                float top = (height - imageHeight) / 2f;
                imageRect.set(0, top, width, top + imageHeight);
            } else {
                float imageWidth = height * imageRatio;
                float left = (width - imageWidth) / 2f;
                imageRect.set(left, 0, left + imageWidth, height);
            }
            minCropSize = Math.min(imageRect.width(), imageRect.height()) * 0.08f;
        }

        private void resetCrop() {
            layoutImageRect(getWidth(), getHeight());
            if (bitmap == null || imageRect.width() <= 0 || imageRect.height() <= 0) {
                cropRect.set(0, 0, 0, 0);
                return;
            }
            float width = imageRect.width() * 0.82f;
            float height = imageRect.height() * 0.82f;
            float left = imageRect.centerX() - width / 2f;
            float top = imageRect.centerY() - height / 2f;
            cropRect.set(left, top, left + width, top + height);
        }

        private boolean nearCorner(float x, float y) {
            float hit = Math.max(40f, minCropSize * 0.28f);
            return distance(x, y, cropRect.left, cropRect.top) < hit
                    || distance(x, y, cropRect.right, cropRect.top) < hit
                    || distance(x, y, cropRect.left, cropRect.bottom) < hit
                    || distance(x, y, cropRect.right, cropRect.bottom) < hit;
        }

        private float distance(float ax, float ay, float bx, float by) {
            float dx = ax - bx;
            float dy = ay - by;
            return (float) Math.sqrt(dx * dx + dy * dy);
        }

        private void moveCrop(float dx, float dy) {
            cropRect.offset(dx, dy);
            if (cropRect.left < imageRect.left) cropRect.offset(imageRect.left - cropRect.left, 0);
            if (cropRect.right > imageRect.right) cropRect.offset(imageRect.right - cropRect.right, 0);
            if (cropRect.top < imageRect.top) cropRect.offset(0, imageRect.top - cropRect.top);
            if (cropRect.bottom > imageRect.bottom) cropRect.offset(0, imageRect.bottom - cropRect.bottom);
        }

        private void resizeCrop(float x, float y) {
            float left = Math.min(x, resizeAnchorX);
            float right = Math.max(x, resizeAnchorX);
            float top = Math.min(y, resizeAnchorY);
            float bottom = Math.max(y, resizeAnchorY);
            left = Math.max(imageRect.left, left);
            right = Math.min(imageRect.right, right);
            top = Math.max(imageRect.top, top);
            bottom = Math.min(imageRect.bottom, bottom);
            if (right - left < minCropSize) {
                if (resizeAnchorX == right) {
                    left = right - minCropSize;
                } else {
                    right = left + minCropSize;
                }
            }
            if (bottom - top < minCropSize) {
                if (resizeAnchorY == bottom) {
                    top = bottom - minCropSize;
                } else {
                    bottom = top + minCropSize;
                }
            }
            cropRect.set(left, top, right, bottom);
        }

        private int clampInt(int value, int min, int max) {
            return Math.max(min, Math.min(max, value));
        }
    }

    private static class PixelPreviewView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private PixelImage image;

        PixelPreviewView(Context context) {
            super(context);
            paint.setStyle(Paint.Style.FILL);
            setBackgroundColor(Color.BLACK);
        }

        void setPixelImage(PixelImage image) {
            this.image = image;
            requestLayout();
            invalidate();
        }

        @Override
        protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
            int width = MeasureSpec.getSize(widthMeasureSpec);
            int previewHeight = image == null ? PIXEL_SIZE : image.height;
            int height = Math.max(1, Math.round(width * (previewHeight / (float) PIXEL_SIZE)));
            setMeasuredDimension(Math.max(1, width), height);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int width = image == null ? PIXEL_SIZE : image.width;
            int height = image == null ? PIXEL_SIZE : image.height;
            float cellW = getWidth() / (float) width;
            float cellH = getHeight() / (float) height;
            for (int row = 0; row < height; row++) {
                for (int column = 0; column < width; column++) {
                    paint.setColor(image == null ? Color.rgb(20, 20, 20) : image.pixels[row * width + column]);
                    canvas.drawRect(column * cellW, row * cellH, (column + 1) * cellW, (row + 1) * cellH, paint);
                }
            }
        }
    }
}
