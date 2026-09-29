import 'dart:async';
import 'package:flutter/material.dart';
import '../models/ipc_models.dart';
import '../services/ipc_client.dart';

class DataView extends StatefulWidget {
  final IPCClient ipc;
  final String selectedDataset;

  const DataView({
    super.key,
    required this.ipc,
    required this.selectedDataset,
  });

  @override
  State<DataView> createState() => _DataViewState();
}

class _DataViewState extends State<DataView> {
  bool _loading = false;
  DataProfile? _profile;
  DatasetSummary? _summary;
  StreamSubscription? _connSub;

  @override
  void initState() {
    super.initState();
    _loadData();
    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted) {
        _loadData();
      }
    });
  }

  @override
  void dispose() {
    _connSub?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(DataView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedDataset != widget.selectedDataset) {
      _loadData();
    }
  }

  Future<void> _loadData() async {
    setState(() => _loading = true);
    try {
      final profRes = await widget.ipc.send('dataset_profile', {'path': widget.selectedDataset});
      if (profRes is Map && mounted) {
        setState(() {
          _profile = DataProfile.fromJson(Map<String, dynamic>.from(profRes));
        });
      }
      final ingestRes = await widget.ipc.send('dataset_ingest', {'path': widget.selectedDataset});
      if (ingestRes is Map && mounted) {
        setState(() {
          _summary = DatasetSummary.fromJson(Map<String, dynamic>.from(ingestRes));
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
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
                  children: [
                    const Text(
                      'UNIVERSAL DATASET INGESTION & PROFILING',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 11,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      widget.selectedDataset,
                      style: const TextStyle(
                        color: Color(0xFF0F172A),
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _summary != null
                          ? '${_summary!.rowCount} rows • ${_summary!.columnCount} channels • SHA-256: ${_summary!.fileHash.substring(0, 12)}...'
                          : 'Profiling telemetry file...',
                      style: const TextStyle(color: Color(0xFF64748B), fontSize: 12),
                    ),
                  ],
                ),
                OutlinedButton.icon(
                  onPressed: _loadData,
                  icon: const Icon(Icons.refresh, size: 14, color: Color(0xFF475569)),
                  label: const Text('RE-PROFILE DATASET', style: TextStyle(color: Color(0xFF475569), fontSize: 11)),
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: Color(0xFFCBD5E1)),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Inferred Roles Banner
            if (_profile != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'AUTONOMOUS VARIABLE ROLE INFERENCE',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.0,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      children: [
                        _rolePill('TARGET METRIC', _profile!.primaryTargetColumn.isNotEmpty ? _profile!.primaryTargetColumn : 'Inferred Target', const Color(0xFF2563EB)),
                        _rolePill('OPERATING LOAD', _profile!.primaryLoadColumn.isNotEmpty ? _profile!.primaryLoadColumn : 'Inferred Load', const Color(0xFF059669)),
                        _rolePill('EQUIPMENT ENTITY', _profile!.primaryEntityColumn, const Color(0xFFD97706)),
                        _rolePill('TEMPORAL INDEX', _profile!.primaryTimeColumn, const Color(0xFF7C3AED)),
                        _rolePill('SAMPLING INTERVAL', _profile!.nominalInterval, const Color(0xFF0284C7)),
                      ],
                    ),
                  ],
                ),
              ),

            const SizedBox(height: 20),

            // Data Quality & Health Score Overview
            if (_profile != null)
              Row(
                children: [
                  Expanded(
                    child: _statBox(
                      'HEALTH SCORE',
                      '${_profile!.dataHealthScore.toStringAsFixed(1)} / 100',
                      'Composite Telemetry Cleanliness',
                      const Color(0xFF059669),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _statBox(
                      'SAMPLING REGULARITY',
                      '${_profile!.samplingRegularityPct.toStringAsFixed(1)}%',
                      'Target: ${_profile!.nominalInterval}',
                      const Color(0xFF2563EB),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _statBox(
                      'OUTAGE GAPS',
                      '${_profile!.irregularGapsCount} gaps',
                      'Segments requiring imputation isolation',
                      const Color(0xFFDC2626),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: _statBox(
                      'MONITORED UNITS',
                      '${_profile!.entities.length}',
                      _profile!.entities.join(', '),
                      const Color(0xFF7C3AED),
                    ),
                  ),
                ],
              ),

            const SizedBox(height: 24),

            // Columns Inspection Table
            Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'DATASET TELEMETRY CHANNELS & SCHEMA PROFILE',
                          style: TextStyle(
                            color: Color(0xFF0F172A),
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 0.8,
                          ),
                        ),
                        Text(
                          '${_profile?.columnCount ?? 0} columns detected',
                          style: const TextStyle(color: Color(0xFF64748B), fontSize: 11),
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1, color: Color(0xFFE2E8F0)),
                  if (_profile != null && _profile!.columnSummaries.isNotEmpty)
                    ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _profile!.columnSummaries.length,
                      separatorBuilder: (context, index) => const Divider(height: 1, color: Color(0xFFF1F5F9)),
                      itemBuilder: (context, index) {
                        final colName = _profile!.columnSummaries.keys.elementAt(index);
                        final colData = _profile!.columnSummaries[colName] as Map<String, dynamic>? ?? {};
                        final nullPct = (colData['missing_percentage'] as num?)?.toDouble() ?? 0.0;
                        final colType = colData['type'] as String? ?? 'numeric';

                        Color roleBadgeColor = const Color(0xFF64748B);
                        String roleLabel = 'Feature';
                        if (colName == _profile!.primaryTargetColumn) {
                          roleBadgeColor = const Color(0xFF2563EB);
                          roleLabel = 'TARGET';
                        } else if (colName == _profile!.primaryLoadColumn) {
                          roleBadgeColor = const Color(0xFF059669);
                          roleLabel = 'LOAD';
                        } else if (colName == _profile!.primaryEntityColumn) {
                          roleBadgeColor = const Color(0xFFD97706);
                          roleLabel = 'ENTITY';
                        } else if (colName == _profile!.primaryTimeColumn) {
                          roleBadgeColor = const Color(0xFF7C3AED);
                          roleLabel = 'TIME';
                        }

                        return Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          child: Row(
                            children: [
                              Container(
                                width: 70,
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: roleBadgeColor.withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(3),
                                ),
                                child: Center(
                                  child: Text(
                                    roleLabel,
                                    style: TextStyle(color: roleBadgeColor, fontSize: 9, fontWeight: FontWeight.bold),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(
                                flex: 3,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      colName,
                                      style: const TextStyle(
                                        color: Color(0xFF0F172A),
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      'Type: $colType',
                                      style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10),
                                    ),
                                  ],
                                ),
                              ),
                              Expanded(
                                flex: 2,
                                child: Row(
                                  children: [
                                    Text(
                                      'Nulls: ${nullPct.toStringAsFixed(1)}%',
                                      style: TextStyle(
                                        color: nullPct > 5 ? const Color(0xFFDC2626) : const Color(0xFF64748B),
                                        fontSize: 11,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              if (colData['min'] != null && colData['max'] != null)
                                Expanded(
                                  flex: 3,
                                  child: Text(
                                    'Range: [${(colData['min'] as num).toStringAsFixed(1)} → ${(colData['max'] as num).toStringAsFixed(1)}]',
                                    style: const TextStyle(color: Color(0xFF475569), fontSize: 11, fontFamily: 'monospace'),
                                    textAlign: TextAlign.right,
                                  ),
                                ),
                            ],
                          ),
                        );
                      },
                    )
                  else if (_summary != null)
                    ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _summary!.columns.length,
                      separatorBuilder: (context, index) => const Divider(height: 1, color: Color(0xFFF1F5F9)),
                      itemBuilder: (context, index) {
                        final col = _summary!.columns[index];
                        return Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          child: Text(col, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 12)),
                        );
                      },
                    )
                  else
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Center(
                        child: Text('No columns loaded. Run autonomous analysis or profiling.', style: TextStyle(color: Color(0xFF64748B))),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _rolePill(String role, String colName, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(role, style: TextStyle(color: color, fontSize: 8, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
          const SizedBox(height: 2),
          Text(colName, style: const TextStyle(color: Color(0xFF0F172A), fontSize: 11, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _statBox(String title, String value, String subtext, Color accent) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: Color(0xFF64748B), fontSize: 9, fontWeight: FontWeight.bold, letterSpacing: 0.6)),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(color: accent, fontSize: 16, fontWeight: FontWeight.w800)),
          const SizedBox(height: 2),
          Text(subtext, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10), overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}
