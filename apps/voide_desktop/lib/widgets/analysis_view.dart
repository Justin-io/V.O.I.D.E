import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../models/ipc_models.dart';
import '../services/ipc_client.dart';

class AnalysisView extends StatefulWidget {
  final IPCClient ipc;
  final String? workspacePath;
  final String selectedEquipment;
  final List<String> availableEquipment;
  final ValueChanged<String>? onEquipmentChanged;
  final VoidCallback? onInvestigate;
  final VoidCallback? onViewVisuals;

  const AnalysisView({
    super.key,
    required this.ipc,
    this.workspacePath,
    this.selectedEquipment = '',
    this.availableEquipment = const [],
    this.onEquipmentChanged,
    this.onInvestigate,
    this.onViewVisuals,
  });

  @override
  State<AnalysisView> createState() => _AnalysisViewState();
}

class _AnalysisViewState extends State<AnalysisView> {
  late String _selectedEquipment;
  List<VisualArtifact> _visuals = [];
  Map<String, dynamic>? _analysisData;
  bool _loading = false;
  StreamSubscription? _connSub;

  @override
  void initState() {
    super.initState();
    _selectedEquipment = widget.selectedEquipment.isNotEmpty
        ? widget.selectedEquipment
        : (widget.availableEquipment.isNotEmpty ? widget.availableEquipment.first : '');
    _loadAnalysisData();
    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted) {
        _loadAnalysisData();
      }
    });
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(AnalysisView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.selectedEquipment.isNotEmpty && widget.selectedEquipment != oldWidget.selectedEquipment) {
      setState(() => _selectedEquipment = widget.selectedEquipment);
    }
  }

  Future<void> _loadAnalysisData() async {
    setState(() => _loading = true);
    try {
      final res = await widget.ipc.send('get_latest_analysis');
      if (res is Map && mounted) {
        setState(() {
          _analysisData = Map<String, dynamic>.from(res);
          final rawVis = res['visuals'] as List?;
          if (rawVis != null) {
            _visuals = rawVis
                .map((v) => VisualArtifact.fromJson(Map<String, dynamic>.from(v)))
                .toList();
          }
          if (_selectedEquipment.isEmpty) {
            final an = _analysisData?['analysis'] as Map<String, dynamic>? ?? {};
            final ents = (an['entities'] as List?)?.map((e) => e.toString()).toList() ?? [];
            if (ents.isNotEmpty) {
              _selectedEquipment = ents.first;
            }
          }
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final analysis = _analysisData?['analysis'] as Map<String, dynamic>? ?? {};
    final modelMetrics = analysis['model_metrics'] as Map<String, dynamic>? ?? {};
    final entities = modelMetrics['entities'] as Map<String, dynamic>? ?? {};

    final equipmentList = widget.availableEquipment.isNotEmpty
        ? widget.availableEquipment
        : (entities.keys.isNotEmpty
            ? entities.keys.map((k) => k.toString()).toList()
            : (_selectedEquipment.isNotEmpty ? [_selectedEquipment] : <String>[]));

    if (_selectedEquipment.isEmpty && equipmentList.isNotEmpty) {
      _selectedEquipment = equipmentList.first;
    }

    final obsVsExpPath = _resolveVisualPath('observed_vs_expected', _selectedEquipment);
    final residualsPath = _resolveVisualPath('residuals', _selectedEquipment);

    final currentEntityModel = entities[_selectedEquipment] as Map<String, dynamic>? ?? {};

    final r2Val = (currentEntityModel['r2'] as num?)?.toDouble() ??
        (analysis['model_r2'] as num?)?.toDouble() ?? 0.0;
    final rmseVal = (currentEntityModel['rmse'] as num?)?.toDouble() ?? 0.0;
    final maeVal = (currentEntityModel['mae'] as num?)?.toDouble() ?? 0.0;
    final cvRmseVal = (currentEntityModel['cv_rmse'] as num?)?.toDouble() ?? 0.0;
    final isAshraeCompliant = currentEntityModel['ashrae_14_compliant'] as bool? ?? (cvRmseVal > 0 && cvRmseVal <= 30.0);

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

            // Header Bar & Equipment Selector
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 16,
              runSpacing: 12,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'CONTEXTUAL ML ANALYSIS & RESIDUAL MODELING',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 11,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Expected-Behaviour Regression & Residual Envelopes',
                      style: TextStyle(color: Color(0xFF0F172A), fontSize: 20, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _selectedEquipment.isNotEmpty
                          ? 'Active Equipment: $_selectedEquipment • Multi-variate Contextual Predictor'
                          : 'No equipment selected • Baseline models pending execution',
                      style: const TextStyle(color: Color(0xFF64748B), fontSize: 12),
                    ),
                  ],
                ),
                if (equipmentList.isNotEmpty)
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                    ...equipmentList.map((eq) {
                      final isSel = _selectedEquipment == eq;
                      return ChoiceChip(
                        label: Text(
                          eq,
                          style: TextStyle(
                            color: isSel ? Colors.white : const Color(0xFF334155),
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        selected: isSel,
                        selectedColor: const Color(0xFF2563EB),
                        backgroundColor: const Color(0xFFFFFFFF),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(4),
                          side: BorderSide(
                            color: isSel ? const Color(0xFF2563EB) : const Color(0xFFCBD5E1),
                          ),
                        ),
                        onSelected: (selected) {
                          if (selected) {
                            setState(() => _selectedEquipment = eq);
                            widget.onEquipmentChanged?.call(eq);
                          }
                        },
                      );
                    }),
                    if (widget.onInvestigate != null)
                      OutlinedButton.icon(
                        onPressed: widget.onInvestigate,
                        icon: const Icon(Icons.biotech_outlined, size: 14, color: Color(0xFF2563EB)),
                        label: const Text('TRIAGE ANOMALIES', style: TextStyle(color: Color(0xFF2563EB), fontSize: 11)),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Color(0xFF93C5FD)),
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                        ),
                      ),
                    if (widget.onViewVisuals != null)
                      OutlinedButton.icon(
                        onPressed: widget.onViewVisuals,
                        icon: const Icon(Icons.image_outlined, size: 14, color: Color(0xFF475569)),
                        label: const Text('SCHEMATICS', style: TextStyle(color: Color(0xFF475569), fontSize: 11)),
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Color(0xFFCBD5E1)),
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                        ),
                      ),
                  ],
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Methodology banner
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Row(
                children: const [
                  Icon(Icons.auto_graph, color: Color(0xFF2563EB), size: 24),
                  SizedBox(width: 14),
                  Expanded(
                    child: Text(
                      'Contextual Residual Principle: High power draw during legitimate peak building thermal load is NOT an anomaly. '
                      'Anomalies are detected when Observed Energy consistently deviates from learned Expected Energy '
                      'under identical cooling rate, temperature lift, and weather context (\u0394 = Observed - Expected > 2.5\u03c3 for \u2265 3 consecutive steps).',
                      style: TextStyle(color: Color(0xFF334155), fontSize: 12, height: 1.4),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Regression Performance Metrics
            LayoutBuilder(
              builder: (context, constraints) {
                final isNarrow = constraints.maxWidth < 700;
                final metrics = [
                  _metricCard(
                    'REGRESSION BASELINE FIT',
                    r2Val > 0 ? 'R\u00b2 = ${r2Val.toStringAsFixed(3)}' : 'R\u00b2 = N/A',
                    '$_selectedEquipment Contextual Baseline',
                    const Color(0xFF059669),
                  ),
                  _metricCard(
                    'ASHRAE GUIDELINE 14',
                    cvRmseVal > 0 ? 'CV(RMSE): ${cvRmseVal.toStringAsFixed(1)}%' : 'N/A',
                    isAshraeCompliant ? 'PASS (\u2264 30% hourly limit)' : 'Evaluate fit',
                    isAshraeCompliant ? const Color(0xFF059669) : const Color(0xFFDC2626),
                  ),
                  _metricCard(
                    'ROOT MEAN SQ ERROR',
                    rmseVal > 0 ? '${rmseVal.toStringAsFixed(2)} kWh' : 'N/A',
                    'Typical Operating Residual',
                    const Color(0xFF2563EB),
                  ),
                  _metricCard(
                    'MEAN ABSOLUTE ERROR',
                    maeVal > 0 ? '${maeVal.toStringAsFixed(2)} kWh' : 'N/A',
                    'Average Prediction Deviation',
                    const Color(0xFFD97706),
                  ),
                ];

                if (isNarrow) {
                  return Column(
                    children: metrics.map((m) => Padding(padding: const EdgeInsets.only(bottom: 12), child: m)).toList(),
                  );
                }

                return Row(
                  children: metrics.map((m) => Expanded(child: Padding(padding: const EdgeInsets.symmetric(horizontal: 6), child: m))).toList(),
                );
              },
            ),

            const SizedBox(height: 28),

            // Visual Chart 1: Observed vs Expected
            const Text(
              'OBSERVED SENSOR TELEMETRY VS EXPECTED CONTEXTUAL BASELINE',
              style: TextStyle(
                color: Color(0xFF64748B),
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
              ),
            ),
            const SizedBox(height: 12),
            _chartSurface(obsVsExpPath, 'Observed vs Expected Baseline Curve ($_selectedEquipment)'),

            const SizedBox(height: 28),

            // Visual Chart 2: Residual Analysis
            const Text(
              'CONTEXTUAL RESIDUAL PROFILE & PERSISTENT ANOMALY ENVELOPE',
              style: TextStyle(
                color: Color(0xFF64748B),
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
              ),
            ),
            const SizedBox(height: 12),
            _chartSurface(residualsPath, 'Contextual Residuals & \u00b12.5\u03c3 Envelope ($_selectedEquipment)'),
          ],
        ),
      ),
    );
  }

  Widget _metricCard(String title, String value, String subtext, Color accent) {
    return Container(
      padding: const EdgeInsets.all(16),
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
          Text(title, style: const TextStyle(color: Color(0xFF64748B), fontSize: 9, fontWeight: FontWeight.bold, letterSpacing: 0.8)),
          const SizedBox(height: 8),
          Text(value, style: TextStyle(color: accent, fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(subtext, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11), overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }

  String _resolveVisualPath(String type, String equipmentId) {
    final eq = equipmentId.toLowerCase();
    final eqAlnum = eq.replaceAll(RegExp(r'[^a-z0-9]'), '');
    final eqDash = eq.replaceAll(RegExp(r'[^a-z0-9]+'), '-');
    final eqUnder = eq.replaceAll(RegExp(r'[^a-z0-9]+'), '_');
    final visualsDir = '${widget.workspacePath}/visuals';

    // 1. Check registered artifacts from backend
    for (final v in _visuals) {
      final vPath = v.filePath.toLowerCase();
      final typeMatches = (type == 'observed_vs_expected' &&
              (v.visualType == 'observed_vs_expected' || vPath.contains('obs_vs_exp') || vPath.contains('observed_vs_expected'))) ||
          (type == 'residuals' &&
              (v.visualType == 'residuals' || vPath.contains('residual')));

      if (typeMatches) {
        if (vPath.contains(eqAlnum) || vPath.contains(eqDash) || vPath.contains(eqUnder)) {
          if (File(v.filePath).existsSync()) {
            return v.filePath;
          }
        }
      }
    }

    // 2. Check candidate filenames directly on disk
    final candidates = <String>[];
    if (type == 'observed_vs_expected') {
      candidates.addAll([
        '$visualsDir/obs_vs_exp_$eqDash.png',
        '$visualsDir/obs_vs_exp_$eqAlnum.png',
        '$visualsDir/obs_vs_exp_$eqUnder.png',
        '$visualsDir/observed_vs_expected_$eqDash.png',
        '$visualsDir/observed_vs_expected_$eqAlnum.png',
        '$visualsDir/observed_vs_expected_$eqUnder.png',
      ]);
    } else if (type == 'residuals') {
      candidates.addAll([
        '$visualsDir/residuals_$eqDash.png',
        '$visualsDir/residuals_$eqAlnum.png',
        '$visualsDir/residuals_$eqUnder.png',
      ]);
    }

    for (final c in candidates) {
      if (File(c).existsSync()) return c;
    }

    // 3. Fallback scan directory for partial matches
    final dir = Directory(visualsDir);
    if (dir.existsSync()) {
      try {
        final prefix = type == 'residuals' ? 'residuals' : 'obs';
        for (final entry in dir.listSync()) {
          if (entry is File && entry.path.endsWith('.png')) {
            final fname = entry.path.split('/').last.toLowerCase();
            if (fname.startsWith(prefix) && (fname.contains(eqAlnum) || fname.contains(eqDash) || fname.contains(eqUnder))) {
              return entry.path;
            }
          }
        }
      } catch (_) {}
    }

    return candidates.isNotEmpty ? candidates.first : '$visualsDir/obs_vs_exp_$eqDash.png';
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

  Widget _chartSurface(String imagePath, String title) {
    final file = File(imagePath);
    final exists = file.existsSync();

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
                Text(title, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontWeight: FontWeight.bold)),
                if (exists)
                  Row(
                    children: [
                      Text(
                        imagePath.split('/').last,
                        style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10, fontFamily: 'monospace'),
                      ),
                      const SizedBox(width: 8),
                      InkWell(
                        onTap: () => _showImageDialog(imagePath, title),
                        child: const Tooltip(
                          message: 'View Fullscreen Interactive Plot',
                          child: Icon(Icons.fullscreen, size: 18, color: Color(0xFF2563EB)),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),
          const Divider(height: 1, color: Color(0xFFE2E8F0)),
          if (exists)
            InkWell(
              onTap: () => _showImageDialog(imagePath, title),
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(bottom: Radius.circular(6)),
                child: Image.file(
                  file,
                  width: double.infinity,
                  fit: BoxFit.contain,
                ),
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 48),
              child: Center(
                child: Column(
                  children: [
                    const Icon(Icons.stacked_line_chart, size: 36, color: Color(0xFF94A3B8)),
                    const SizedBox(height: 12),
                    Text(
                      'Chart not yet rendered for $_selectedEquipment',
                      style: const TextStyle(color: Color(0xFF0F172A), fontSize: 13, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Click "RUN ANALYSIS" in the top bar to generate high-resolution visual plots.',
                      style: TextStyle(color: Color(0xFF64748B), fontSize: 11),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
