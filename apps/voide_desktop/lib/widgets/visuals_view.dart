import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../models/ipc_models.dart';
import '../services/ipc_client.dart';

class VisualsView extends StatefulWidget {
  final IPCClient ipc;
  final String workspacePath;

  const VisualsView({super.key, required this.ipc, required this.workspacePath});

  @override
  State<VisualsView> createState() => _VisualsViewState();
}

class _VisualsViewState extends State<VisualsView> {
  List<VisualArtifact> _artifacts = [];
  bool _loading = false;
  StreamSubscription? _connSub;

  @override
  void initState() {
    super.initState();
    _loadVisuals();
    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted && _artifacts.isEmpty) {
        _loadVisuals();
      }
    });
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }

  Future<void> _loadVisuals() async {
    setState(() => _loading = true);
    try {
      final res = await widget.ipc.send('get_visual_artifacts');
      if (res is List && mounted) {
        setState(() {
          _artifacts = res.map((i) => VisualArtifact.fromJson(Map<String, dynamic>.from(i))).toList();
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  void _showImageDialog(String filePath, String title) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.white,
        insetPadding: const EdgeInsets.all(24),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(title, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 13, fontWeight: FontWeight.bold)),
                  IconButton(
                    icon: const Icon(Icons.close, color: Color(0xFF64748B), size: 18),
                    onPressed: () => Navigator.pop(ctx),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: Color(0xFFE2E8F0)),
            Flexible(
              child: InteractiveViewer(
                child: Image.file(File(filePath)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final visualsDir = '${widget.workspacePath}/visuals';
    var schematicFile = File('$visualsDir/chiller_schematic.png');

    final Map<String, VisualArtifact> uniqueArtifacts = {};

    // 1. Add from IPC artifacts
    for (final art in _artifacts) {
      if (art.visualType == 'schematic' || art.filePath.contains('schematic')) continue;
      final fname = art.filePath.split('/').last.toLowerCase();
      final cleanKey = fname
          .replaceAll('observed_vs_expected', 'obs')
          .replaceAll('obs_vs_exp', 'obs')
          .replaceAll('-', '')
          .replaceAll('_', '')
          .replaceAll('.png', '');
      if (File(art.filePath).existsSync()) {
        uniqueArtifacts.putIfAbsent(cleanKey, () => art);
      }
    }

    // 2. Add from visuals directory on disk if not already present
    if (Directory(visualsDir).existsSync()) {
      final dir = Directory(visualsDir);
      for (final entity in dir.listSync()) {
        if (entity is File && entity.path.endsWith('.png')) {
          final fname = entity.path.split('/').last;
          if (fname.contains('schematic')) continue;
          final cleanKey = fname.toLowerCase()
              .replaceAll('observed_vs_expected', 'obs')
              .replaceAll('obs_vs_exp', 'obs')
              .replaceAll('-', '')
              .replaceAll('_', '')
              .replaceAll('.png', '');
          if (!uniqueArtifacts.containsKey(cleanKey)) {
            String type = 'chart';
            if (fname.startsWith('obs') || fname.contains('observed_vs_expected')) type = 'observed_vs_expected';
            if (fname.startsWith('residuals')) type = 'residuals';
            if (fname.startsWith('anomaly_zoom')) type = 'anomaly_zoom';

            uniqueArtifacts[cleanKey] = VisualArtifact(
              artifactId: 'art-$fname',
              visualType: type,
              title: fname.replaceAll('.png', '').replaceAll('_', ' ').toUpperCase(),
              filePath: entity.path,
            );
          }
        }
      }
    }

    final displayArtifacts = uniqueArtifacts.values.toList();

    return Container(
      color: const Color(0xFFF8FAFC),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_loading) ...[
              const LinearProgressIndicator(
                minHeight: 3,
                backgroundColor: Color(0xFFE2E8F0),
                color: Color(0xFF2563EB),
              ),
              const SizedBox(height: 16),
            ],

            // Top Header
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 16,
              runSpacing: 12,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: const [
                    Text(
                      'VISUAL INTELLIGENCE & ENGINEERING SCHEMATICS',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 11,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Publication-Grade Baseline Visualizations & Flow Diagrams',
                      style: TextStyle(color: Color(0xFF0F172A), fontSize: 20, fontWeight: FontWeight.w800),
                    ),
                  ],
                ),
                OutlinedButton.icon(
                  onPressed: _loadVisuals,
                  icon: const Icon(Icons.refresh, size: 14, color: Color(0xFF475569)),
                  label: const Text('RELOAD ARTIFACTS', style: TextStyle(color: Color(0xFF475569), fontSize: 11)),
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: Color(0xFFCBD5E1)),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Physical Chiller System Schematic
            const Text(
              'EQUIPMENT REFRIGERATION CYCLE & SENSOR TOPOLOGY',
              style: TextStyle(color: Color(0xFF64748B), fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.0),
            ),
            const SizedBox(height: 12),
            _schematicCard(schematicFile),

            const SizedBox(height: 28),

            // Generated Telemetry & Residual Plots
            const Text(
              'ANALYTICAL PLOTS & REGRESSION EVIDENCE GALLERIES',
              style: TextStyle(color: Color(0xFF64748B), fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.0),
            ),
            const SizedBox(height: 12),

            if (displayArtifacts.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(48),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Center(
                  child: Column(
                    children: const [
                      Icon(Icons.photo_library_outlined, size: 40, color: Color(0xFF94A3B8)),
                      SizedBox(height: 12),
                      Text(
                        'No visual artifacts rendered yet',
                        style: TextStyle(color: Color(0xFF0F172A), fontWeight: FontWeight.bold, fontSize: 13),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Execute "RUN ANALYSIS" from the top bar to render publication-grade plots.',
                        style: TextStyle(color: Color(0xFF64748B), fontSize: 11),
                      ),
                    ],
                  ),
                ),
              )
            else
              GridView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: 16,
                  mainAxisSpacing: 16,
                  childAspectRatio: 1.4,
                ),
                itemCount: displayArtifacts.length,
                itemBuilder: (context, idx) {
                  final art = displayArtifacts[idx];
                  final file = File(art.filePath);
                  final exists = file.existsSync();

                  return Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: const Color(0xFFE2E8F0)),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.02),
                          blurRadius: 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Text(
                                  art.title,
                                  style: const TextStyle(color: Color(0xFF0F172A), fontSize: 11, fontWeight: FontWeight.bold),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              if (exists)
                                InkWell(
                                  onTap: () => _showImageDialog(art.filePath, art.title),
                                  child: const Icon(Icons.fullscreen, size: 16, color: Color(0xFF2563EB)),
                                ),
                            ],
                          ),
                        ),
                        const Divider(height: 1, color: Color(0xFFE2E8F0)),
                        Expanded(
                          child: exists
                              ? InkWell(
                                  onTap: () => _showImageDialog(art.filePath, art.title),
                                  child: ClipRRect(
                                    borderRadius: const BorderRadius.vertical(bottom: Radius.circular(6)),
                                    child: Image.file(file, fit: BoxFit.contain, width: double.infinity),
                                  ),
                                )
                              : const Center(
                                  child: Text('File not found', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
                                ),
                        ),
                      ],
                    ),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _schematicCard(File schematicFile) {
    final exists = schematicFile.existsSync();
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFFE2E8F0)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.02),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Physical Loop Schematic & Subsystem Sensor Layout',
                  style: TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontWeight: FontWeight.bold),
                ),
                if (exists)
                  InkWell(
                    onTap: () => _showImageDialog(schematicFile.path, 'Equipment Subsystem Schematic'),
                    child: const Text('FULLSCREEN', style: TextStyle(color: Color(0xFF2563EB), fontSize: 10, fontWeight: FontWeight.bold)),
                  ),
              ],
            ),
          ),
          const Divider(height: 1, color: Color(0xFFE2E8F0)),
          if (exists)
            ClipRRect(
              borderRadius: const BorderRadius.vertical(bottom: Radius.circular(6)),
              child: Image.file(schematicFile, width: double.infinity, fit: BoxFit.contain),
            )
          else
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(
                child: Text('Run autonomous analysis to generate system schematic.', style: TextStyle(color: Color(0xFF64748B), fontSize: 11)),
              ),
            ),
        ],
      ),
    );
  }
}
