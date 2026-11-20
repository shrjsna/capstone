# index.html Structural Diff Report

## 1. Summary of Changes
- **Fonts / External Links REMOVED**: Removed 3 Google Fonts `<link>` tags (lines 7-9 in backup).
- **Outer Layout Wrapper ADDED**: Added `<div class="fx-frame">` wrapping `<header>`, `<nav>`, and all 6 `<main>` tab containers.
- **Script Tag ADDED**: Added `<script src="fx.js" defer></script>` after `app.js`.
- **Tab 1 Hero ADDED**: Added `<section class="fx-hero">` at the start of `#tab-alerts` containing `.fx-hero-left`, `#fx-btn-open-alerts`, `.fx-tags-container` (9 draggable pills), `.fx-stats-strip` (3 stat cells), and `#fx-tunnel-zone` (SVG wireframe tunnel).
- **Tab Title Bands ADDED**: Added `<div class="fx-title-band">` with skewed accent slash as first child to tabs: `#tab-stream`, `#tab-zones`, `#tab-control`, `#tab-users`, `#tab-audit`.

## 2. Reparented Elements (Parent Changes)
Total reparented IDs: 1

| Element ID | Backup Parent | Current Parent |
|---|---|---|
| `#login-modal` | `sub-panel` | `sidebar-panel` |

## 3. Raw Unified Diff (First 150 lines)
```diff
--- backup/index.html
+++ current/index.html
@@ -4,14 +4,14 @@
   <meta charset="UTF-8">
   <meta name="viewport" content="width=device-width, initial-scale=1.0">
   <title>AEGIS — Collaborative AI Safety Operations Console</title>
-  <link rel="preconnect" href="https://fonts.googleapis.com">
-  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
-  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700&display=swap" rel="stylesheet">
   <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%23FF6A00' d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/%3E%3C/svg%3E">
   <link rel="alternate icon" href="favicon.ico">
   <link rel="stylesheet" href="styles.css">
 </head>
 <body>
+
+  <!-- FX Editorial Frame Wrap -->
+  <div class="fx-frame">
 
   <!-- Top Navigation Header -->
   <header class="app-header">
@@ -78,6 +78,78 @@
   <!-- ===== TAB: ALERT FEED ===== -->
   <main class="console-grid tab-content active" id="tab-alerts">
 
+    <!-- FX Dark Editorial Hero with Wireframe Tunnel -->
+    <section class="fx-hero">
+      <div class="fx-hero-left">
+        <div class="fx-hero-title-box">
+          <h1 class="fx-hero-title">
+            <span class="fx-hero-slash fx-slash-line-1">EDGE-CLOUD / SAFETY FOR</span>
+            <span class="fx-hero-slash fx-slash-line-2">INDUSTRIAL FLOORS</span>
+          </h1>
+        </div>
+        <p class="fx-hero-sub">Autonomous edge surveillance, human-in-the-loop bandit learning, and zero raw-footage leakage across industrial deployments.</p>
+
+        <div class="fx-hero-actions">
+          <button type="button" class="btn-primary fx-btn-open-alerts" id="fx-btn-open-alerts">
+            <span>Open Alerts</span>
+            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="7 13 12 18 17 13"/><polyline points="7 6 12 11 17 6"/></svg>
+          </button>
+          <span class="fx-hero-hint">Drag a tag onto the tunnel to pin it</span>
+        </div>
+
+        <!-- Draggable physics tag pills -->
+        <div class="fx-tags-container" id="fx-tags-field">
+          <span class="fx-tag-pill" data-tag="YOLOv11n">YOLOv11n</span>
+          <span class="fx-tag-pill" data-tag="ByteTrack">ByteTrack</span>
+          <span class="fx-tag-pill" data-tag="LinUCB">LinUCB</span>
+          <span class="fx-tag-pill" data-tag="FedAvg">FedAvg</span>
+          <span class="fx-tag-pill" data-tag="Flower">Flower</span>
+          <span class="fx-tag-pill" data-tag="FastAPI">FastAPI</span>
+          <span class="fx-tag-pill" data-tag="RBAC">RBAC</span>
+          <span class="fx-tag-pill" data-tag="MJPEG">MJPEG</span>
+          <span class="fx-tag-pill" data-tag="Face blur">Face blur</span>
+        </div>
+
+        <!-- Hero Stats Strip -->
+        <div class="fx-stats-strip">
+          <div class="fx-stat-cell">
+            <span class="fx-stat-label">Alerts Shown</span>
+            <span class="fx-stat-val" id="fx-stat-shown">0</span>
+          </div>
+          <div class="fx-stat-cell">
+            <span class="fx-stat-label">Unreviewed</span>
+            <span class="fx-stat-val" id="fx-stat-unreviewed">0</span>
+          </div>
+          <div class="fx-stat-cell">
+            <span class="fx-stat-label">Policy Version</span>
+            <span class="fx-stat-val" id="fx-stat-policy">v1.0.0</span>
+          </div>
+        </div>
+      </div>
+
+      <div class="fx-hero-tunnel-wrap" id="fx-tunnel-zone">
+        <div class="fx-tunnel-header">
+          <span class="fx-tunnel-label">NEURAL PIPELINE TUNNEL</span>
+          <span class="fx-tunnel-status">INTERACTIVE PROJECTION</span>
+        </div>
+        <div class="fx-tunnel-canvas-box" id="fx-tunnel-container">
+          <svg id="fx-tunnel-svg" viewBox="0 0 400 320" preserveAspectRatio="none">
+            <defs>
+              <radialGradient id="tunnelCoreGrad" cx="50%" cy="50%" r="50%">
+                <stop offset="0%" stop-color="#12100f" stop-opacity="0.95"/>
+                <stop offset="40%" stop-color="#1c1918" stop-opacity="0.8"/>
+                <stop offset="100%" stop-color="#221e1d" stop-opacity="0"/>
+              </radialGradient>
+            </defs>
+            <g id="fx-tunnel-spokes"></g>
+            <g id="fx-tunnel-rects"></g>
+            <g id="fx-tunnel-dots"></g>
+            <circle id="fx-tunnel-core" cx="200" cy="160" r="28" fill="url(#tunnelCoreGrad)"></circle>
+          </svg>
+        </div>
+      </div>
+    </section>
+
     <section class="panel feed-panel">
       <div class="panel-header">
         <div class="panel-title-group">
@@ -171,6 +243,12 @@
 
   <!-- ===== TAB: LIVE STREAM ===== -->
   <main class="stream-layout tab-content" id="tab-stream">
+
+    <div class="fx-title-band">
+      <div class="fx-title-wrap">
+        <span class="fx-title-text">REAL-TIME SURVEILLANCE / <span class="fx-slash-accent">LIVE CAMERA STREAM</span></span>
+      </div>
+    </div>
 
     <!-- Left: controls -->
     <aside class="panel stream-controls-panel">
@@ -312,6 +390,12 @@
   <!-- ===== TAB: DRAW ZONE ===== -->
   <main class="zone-layout tab-content" id="tab-zones">
 
+    <div class="fx-title-band">
+      <div class="fx-title-wrap">
+        <span class="fx-title-text">GEOMETRIC PERIMETER / <span class="fx-slash-accent">RESTRICTED SAFETY ZONES</span></span>
+      </div>
+    </div>
+
     <!-- Left: controls -->
     <aside class="panel zone-controls-panel">
       <div class="panel-header compact">
@@ -467,6 +551,12 @@
 
   <!-- ===== TAB: CONTROL PANEL ===== -->
   <main class="control-layout tab-content" id="tab-control">
+
+    <div class="fx-title-band">
+      <div class="fx-title-wrap">
+        <span class="fx-title-text">SUBPROCESS SUPERVISOR / <span class="fx-slash-accent">ORCHESTRATION PANEL</span></span>
+      </div>
+    </div>
 
     <section class="panel control-main-panel">
       <div class="panel-header">
@@ -661,6 +751,12 @@
 
   <!-- ===== TAB: USERS & EDGE KEYS (ADMIN ONLY) ===== -->
   <main class="console-grid tab-content" id="tab-users">
+
+    <div class="fx-title-band">
+      <div class="fx-title-wrap">
+        <span class="fx-title-text">SECURITY ACCESS / <span class="fx-slash-accent">USERS &amp; EDGE KEYS</span></span>
+      </div>
+    </div>
     <section class="panel feed-panel">
       <div class="panel-header">

```
