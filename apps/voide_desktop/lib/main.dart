import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'models/ipc_models.dart';
import 'services/ipc_client.dart';
import 'widgets/agent_panel.dart';
import 'widgets/browser_surface.dart';
import 'widgets/command_bar.dart';
import 'widgets/editor_surface.dart';
import 'widgets/workspace_rail.dart';
import 'widgets/overview_view.dart';
import 'widgets/data_view.dart';
import 'widgets/analysis_view.dart';
import 'widgets/investigation_view.dart';
import 'widgets/visuals_view.dart';
import 'widgets/report_view.dart';

void main() {
  runApp(const VoideApp());
}

class VoideApp extends StatelessWidget {
  const VoideApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'V.O.I.D.E. | Engineering Intelligence Workstation',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.light,
        scaffoldBackgroundColor: const Color(0xFFF8FAFC),
        fontFamily: 'sans-serif',
        colorScheme: const ColorScheme.light(
          primary: Color(0xFF2563EB),
          surface: Color(0xFFFFFFFF),
        ),
        dividerColor: const Color(0xFFE2E8F0),
        textSelectionTheme: const TextSelectionThemeData(
          cursorColor: Color(0xFF2563EB),
          selectionColor: Color(0xFFBFDBFE),
          selectionHandleColor: Color(0xFF2563EB),
        ),
      ),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: const TextScaler.linear(1.18),
        ),
        child: child!,
      ),
      home: const VoideWorkspaceScreen(),
    );
  }
}

class VoideWorkspaceScreen extends StatefulWidget {
  const VoideWorkspaceScreen({super.key});

  @override
  State<VoideWorkspaceScreen> createState() => _VoideWorkspaceScreenState();
}

class _VoideWorkspaceScreenState extends State<VoideWorkspaceScreen> {
  final IPCClient _ipc = IPCClient();
  bool _isConnected = false;
  String _workspacePath = '';

  RailTab _activeRailTab = RailTab.overview;
  String _selectedDataset = 'development_dataset.csv';
  List<String> _availableDatasets = ['development_dataset.csv'];
  List<String> _availableEquipment = [];
  String _selectedEquipment = '';
  String? _selectedAnomalyId;
  bool _isAgentPanelOpen = true;

  bool _isPipelineRunning = false;
  String _pipelineStage = '';
  double _pipelineProgress = 0.0;
  int _anomalyCount = 0;

  List<FileEntry> _files = [];
  String _activeFilePath = '';
  final List<EditorTab> _openTabs = [];
  final List<AuditEvent> _events = [];
  final List<String> _terminalLogs = [];

  final List<StreamSubscription> _subscriptions = [];

  @override
  void initState() {
    super.initState();
    _setupSubscriptions();
    _ipc.connect();
  }

  void _setupSubscriptions() {
    _subscriptions.add(_ipc.connectionStream.listen((connected) {
      if (mounted) setState(() => _isConnected = connected);
      if (connected) {
        if (_ipc.serverWorkspace != null && mounted) {
          setState(() => _workspacePath = _ipc.serverWorkspace!);
        }
        _initWorkspaceData();
      }
    }));

    _subscriptions.add(_ipc.helloStream.listen((hello) {
      if (mounted && hello['workspace'] != null) {
        setState(() => _workspacePath = hello['workspace'] as String);
        _initWorkspaceData();
      }
    }));

    _subscriptions.add(_ipc.eventStream.listen((event) {
      if (mounted) {
        setState(() {
          _events.insert(0, event);
          if (event.eventType == 'TOOL_EXECUTED') {
            final tool = event.data["tool"] ?? "";
            final status = event.data["status"] ?? "";
            _terminalLogs.add('[AGENT] $tool → $status');
          }
        });
      }
    }));

    _subscriptions.add(_ipc.toolStream.listen((data) {
      final tool = data['tool'] as Map<String, dynamic>?;
      if (tool != null && mounted) {
        final name = tool["tool"] ?? "";
        final target = tool["path"] ?? tool["command"] ?? tool["query"] ?? "";
        final status = tool["status"] ?? "";
        final targetDesc = target.toString().isNotEmpty ? ' → $target' : '';
        setState(() {
          _terminalLogs.add('[TOOL] $name$targetDesc ($status)');
        });
        if (tool['tool'] == 'write_file' && tool['path'] != null) {
          final path = tool['path'] as String;
          _loadFiles().then((_) => _openFileInTab(path));
        }
      }
    }));

    _subscriptions.add(_ipc.terminalStream.listen((data) {
      if (mounted && data['output'] != null) {
        setState(() => _terminalLogs.add(data['output'] as String));
      }
    }));

    _subscriptions.add(_ipc.pipelineStageStream.listen((data) {
      if (mounted) {
        final stage = (data['stage'] ?? '').toString();
        final progress = (data['progress'] as num?)?.toDouble() ?? 0.0;
        setState(() {
          _pipelineStage = stage;
          _pipelineProgress = progress;
          if (stage == 'COMPLETE' || stage == 'COMPLETED') {
            _isPipelineRunning = false;
          }
        });
      }
    }));
  }

  Future<void> _initWorkspaceData() async {
    await _loadDatasets();
    await _loadLatestAnalysis();
    await _loadFiles();
  }

  Future<void> _loadDatasets() async {
    try {
      final res = await _ipc.send('list_datasets');
      if (res is List && mounted) {
        final names = res.map((d) => (d['name'] ?? '').toString()).where((n) => n.isNotEmpty).toList();
        if (names.isNotEmpty) {
          setState(() {
            _availableDatasets = names;
            if (!_availableDatasets.contains(_selectedDataset)) {
              _selectedDataset = _availableDatasets.first;
            }
          });
        }
      }
    } catch (_) {}

    // Check workspace datasets directory
    if (_workspacePath.isNotEmpty) {
      final dsDir = Directory('$_workspacePath/datasets');
      if (dsDir.existsSync()) {
        final csvs = dsDir.listSync().whereType<File>().where((f) => f.path.endsWith('.csv')).map((f) => f.path.split('/').last).toList();
        if (csvs.isNotEmpty && mounted) {
          setState(() {
            final union = {..._availableDatasets, ...csvs}.toList();
            _availableDatasets = union;
          });
        }
      }
    }
  }

  Future<void> _loadLatestAnalysis() async {
    try {
      final res = await _ipc.send('get_latest_analysis');
      if (res is Map && mounted) {
        final analysis = res['analysis'] as Map<String, dynamic>?;
        final rawAnoms = res['anomalies'] as List?;
        if (analysis != null) {
          final anomCount = (analysis['anomalies_detected'] as num?)?.toInt() ?? (rawAnoms?.length ?? 0);
          final modelMetrics = analysis['model_metrics'] as Map<String, dynamic>? ?? {};
          final entModels = modelMetrics['entities'] as Map<String, dynamic>? ?? {};
          final entList = entModels.keys.toList();

          setState(() {
            _anomalyCount = anomCount;
            if (entList.isNotEmpty) {
              _availableEquipment = entList;
              if (_selectedEquipment.isEmpty || !_availableEquipment.contains(_selectedEquipment)) {
                _selectedEquipment = _availableEquipment.first;
              }
            }
          });
        }
      }

      // If equipment still empty, profile dataset to find entities
      if (_availableEquipment.isEmpty) {
        final profRes = await _ipc.send('dataset_profile', {'path': _selectedDataset});
        if (profRes is Map && mounted) {
          final profile = DataProfile.fromJson(Map<String, dynamic>.from(profRes));
          if (profile.entities.isNotEmpty) {
            setState(() {
              _availableEquipment = profile.entities;
              if (_selectedEquipment.isEmpty || !_availableEquipment.contains(_selectedEquipment)) {
                _selectedEquipment = _availableEquipment.first;
              }
            });
          }
        }
      }
    } catch (_) {}
  }

  Future<void> _runPipeline() async {
    setState(() {
      _isPipelineRunning = true;
      _pipelineStage = 'INITIALIZING';
      _pipelineProgress = 0.05;
    });

    try {
      final res = await _ipc.send('run_analysis_pipeline', {
        'path': _selectedDataset,
        'dataset_name': _selectedDataset,
      });

      if (mounted) {
        setState(() {
          _isPipelineRunning = false;
          _pipelineStage = 'COMPLETE';
          _pipelineProgress = 1.0;
        });

        if (res is Map) {
          final anomCount = (res['anomalies_detected'] as num?)?.toInt() ?? 0;
          final entList = (res['entities'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [];
          setState(() {
            _anomalyCount = anomCount;
            if (entList.isNotEmpty) {
              _availableEquipment = entList;
              if (_selectedEquipment.isEmpty || !_availableEquipment.contains(_selectedEquipment)) {
                _selectedEquipment = _availableEquipment.first;
              }
            }
          });

          await _loadLatestAnalysis();

          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Analysis Pipeline Completed: $anomCount anomalies detected across ${entList.length} equipment units.'),
                backgroundColor: const Color(0xFF2563EB),
                duration: const Duration(seconds: 4),
              ),
            );
          }
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isPipelineRunning = false;
          _pipelineStage = 'FAILED';
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Pipeline execution error: $e'),
            backgroundColor: const Color(0xFFDC2626),
          ),
        );
      }
    }
  }

  void _showDatasetSelectorDialog() {
    final customPathCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        title: Row(
          children: const [
            Icon(Icons.storage, size: 18, color: Color(0xFF2563EB)),
            SizedBox(width: 8),
            Text('Select or Upload Telemetry Dataset', style: TextStyle(color: Color(0xFF0F172A), fontSize: 14, fontWeight: FontWeight.bold)),
          ],
        ),
        content: SizedBox(
          width: 480,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Available Workspace Datasets:', style: TextStyle(color: Color(0xFF64748B), fontSize: 11, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Container(
                decoration: BoxDecoration(
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: _availableDatasets.length,
                  separatorBuilder: (context, index) => const Divider(height: 1, color: Color(0xFFE2E8F0)),
                  itemBuilder: (context, idx) {
                    final ds = _availableDatasets[idx];
                    final isSel = ds == _selectedDataset;
                    return ListTile(
                      dense: true,
                      selected: isSel,
                      selectedTileColor: const Color(0xFFEFF6FF),
                      leading: Icon(Icons.table_chart, size: 16, color: isSel ? const Color(0xFF2563EB) : const Color(0xFF64748B)),
                      title: Text(
                        ds,
                        style: TextStyle(
                          color: isSel ? const Color(0xFF2563EB) : const Color(0xFF0F172A),
                          fontWeight: isSel ? FontWeight.bold : FontWeight.normal,
                          fontSize: 12,
                        ),
                      ),
                      trailing: isSel ? const Icon(Icons.check, size: 16, color: Color(0xFF2563EB)) : null,
                      onTap: () {
                        Navigator.pop(ctx);
                        _switchDataset(ds);
                      },
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),
              const Text('Select External CSV from Filesystem:', style: TextStyle(color: Color(0xFF64748B), fontSize: 11, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: customPathCtrl,
                      style: const TextStyle(fontSize: 11, fontFamily: 'monospace', color: Color(0xFF0F172A)),
                      decoration: const InputDecoration(
                        hintText: '/absolute/path/to/telemetry.csv',
                        hintStyle: TextStyle(color: Color(0xFF94A3B8), fontSize: 11),
                        border: OutlineInputBorder(),
                        isDense: true,
                        contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: () {
                      final path = customPathCtrl.text.trim();
                      if (path.isNotEmpty) {
                        Navigator.pop(ctx);
                        _uploadCustomDataset(path);
                      }
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2563EB),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      elevation: 0,
                    ),
                    child: const Text('INGEST', style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel', style: TextStyle(color: Color(0xFF64748B))),
          ),
        ],
      ),
    );
  }

  Future<void> _switchDataset(String datasetName) async {
    setState(() {
      _selectedDataset = datasetName;
      _availableEquipment.clear();
      _selectedEquipment = '';
      _anomalyCount = 0;
    });

    try {
      final profRes = await _ipc.send('dataset_profile', {'path': datasetName});
      if (profRes is Map && mounted) {
        final profile = DataProfile.fromJson(Map<String, dynamic>.from(profRes));
        if (profile.entities.isNotEmpty) {
          setState(() {
            _availableEquipment = profile.entities;
            _selectedEquipment = profile.entities.first;
          });
        }
      }
    } catch (_) {}
  }

  Future<void> _uploadCustomDataset(String filePath) async {
    try {
      final res = await _ipc.send('upload_dataset', {'file_path': filePath});
      if (res is Map && mounted) {
        final name = (res['name'] ?? filePath.split('/').last).toString();
        setState(() {
          if (!_availableDatasets.contains(name)) {
            _availableDatasets.add(name);
          }
          _selectedDataset = name;
        });
        await _switchDataset(name);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Dataset "$name" uploaded and profiled successfully!'),
              backgroundColor: const Color(0xFF059669),
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Upload failed: $e'),
            backgroundColor: const Color(0xFFDC2626),
          ),
        );
      }
    }
  }

  Future<void> _loadFiles() async {
    try {
      final res = await _ipc.send('list_files', {'path': ''});
      if (res is List && mounted) {
        setState(() {
          _files = res
              .map((item) => FileEntry.fromJson(Map<String, dynamic>.from(item)))
              .toList();
        });
      }
    } catch (_) {}
  }

  Future<void> _openFileInTab(String path) async {
    final exists = _openTabs.any((t) => t.path == path);
    if (!exists) {
      try {
        final res = await _ipc.send('read_file', {'path': path});
        if (res is Map && res['content'] != null && mounted) {
          final content = res['content'] as String;
          setState(() {
            _openTabs.add(EditorTab(
              path: path,
              name: path.split('/').last,
              content: content,
            ));
          });
        }
      } catch (_) {}
    }
    if (mounted) {
      setState(() {
        _activeFilePath = path;
        _activeRailTab = RailTab.files;
      });
    }
  }

  Future<void> _saveFile(String path, String content) async {
    try {
      await _ipc.send('write_file', {'path': path, 'content': content});
      setState(() {
        _terminalLogs.add('[SAVED] $path');
        final tabIdx = _openTabs.indexWhere((t) => t.path == path);
        if (tabIdx != -1) {
          _openTabs[tabIdx].content = content;
          _openTabs[tabIdx].isDirty = false;
        }
      });
    } catch (e) {
      setState(() => _terminalLogs.add('[SAVE ERROR] $e'));
    }
  }

  void _closeTab(String path) {
    setState(() {
      _openTabs.removeWhere((t) => t.path == path);
      if (_activeFilePath == path) {
        _activeFilePath = _openTabs.isNotEmpty ? _openTabs.last.path : '';
      }
    });
  }

  Future<void> _openFolder() async {
    final defaultHome = Platform.environment['HOME'] ?? '.';
    final ctrl = TextEditingController(text: _workspacePath.isNotEmpty ? _workspacePath : defaultHome);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        title: const Text('Open Folder', style: TextStyle(color: Color(0xFF0F172A), fontSize: 13, fontWeight: FontWeight.bold)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Enter the absolute path to workspace folder:', style: TextStyle(color: Color(0xFF64748B), fontSize: 11)),
            const SizedBox(height: 10),
            TextField(
              controller: ctrl,
              autofocus: true,
              style: const TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontFamily: 'monospace'),
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                isDense: true,
              ),
              onSubmitted: (_) {
                Navigator.pop(ctx);
                _doOpenFolder(ctrl.text);
              },
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel', style: TextStyle(color: Color(0xFF64748B)))),
          TextButton(onPressed: () {
            Navigator.pop(ctx);
            _doOpenFolder(ctrl.text);
          }, child: const Text('Open', style: TextStyle(color: Color(0xFF2563EB)))),
        ],
      ),
    );
  }

  Future<void> _doOpenFolder(String path) async {
    if (path.isEmpty) return;
    final dir = Directory(path);
    if (!dir.existsSync()) {
      _terminalLogs.add('[ERROR] Folder not found: $path');
      return;
    }
    try {
      await _ipc.send('workspace_open', {'path': path});
    } catch (_) {}
    if (mounted) {
      setState(() {
        _workspacePath = path;
        _openTabs.clear();
        _activeFilePath = '';
      });
    }
    await _loadFiles();
  }

  Future<void> _newFile() async {
    final ctrl = TextEditingController(text: 'analysis_notes.md');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        title: const Text('New Asset', style: TextStyle(color: Color(0xFF0F172A), fontSize: 13, fontWeight: FontWeight.bold)),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          style: const TextStyle(color: Color(0xFF0F172A), fontSize: 12, fontFamily: 'monospace'),
          decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true),
          onSubmitted: (_) {
            Navigator.pop(ctx);
            _doCreateFile(ctrl.text);
          },
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel', style: TextStyle(color: Color(0xFF64748B)))),
          TextButton(onPressed: () {
            Navigator.pop(ctx);
            _doCreateFile(ctrl.text);
          }, child: const Text('Create', style: TextStyle(color: Color(0xFF2563EB)))),
        ],
      ),
    );
  }

  Future<void> _doCreateFile(String name) async {
    if (name.isEmpty) return;
    try {
      await _ipc.send('write_file', {'path': name, 'content': ''});
      await _loadFiles();
      await _openFileInTab(name);
    } catch (e) {
      setState(() => _terminalLogs.add('[ERROR] $e'));
    }
  }

  Future<void> _deleteFile(String path) async {
    try {
      await _ipc.send('delete_file', {'path': path});
      _closeTab(path);
      await _loadFiles();
    } catch (e) {
      setState(() => _terminalLogs.add('[DELETE ERROR] $e'));
    }
  }

  Future<void> _renameFile(String oldPath, String newPath) async {
    try {
      await _ipc.send('rename_file', {'old_path': oldPath, 'new_path': newPath});
      final tabIdx = _openTabs.indexWhere((t) => t.path == oldPath);
      if (tabIdx != -1) {
        final tab = _openTabs[tabIdx];
        setState(() {
          _openTabs[tabIdx] = EditorTab(
            path: newPath,
            name: newPath.split('/').last,
            content: tab.content,
            isDirty: tab.isDirty,
          );
          if (_activeFilePath == oldPath) _activeFilePath = newPath;
        });
      }
      await _loadFiles();
    } catch (e) {
      setState(() => _terminalLogs.add('[RENAME ERROR] $e'));
    }
  }

  void _onTerminalCommand(String command) {
    setState(() => _terminalLogs.add('\$ $command'));
    _ipc.send('terminal_write', {
      'session_id': 'term-user-1',
      'data': '$command\n',
    }).then((_) {
      _ipc.send('terminal_read', {'session_id': 'term-user-1'}).then((res) {
        if (res is Map && res['output'] != null && (res['output'] as String).isNotEmpty) {
          setState(() => _terminalLogs.add(res['output'] as String));
        }
      });
    }).catchError((err) {
      setState(() => _terminalLogs.add('[PTY ERROR] $err'));
    });
  }

  Widget _buildMainSurface() {
    switch (_activeRailTab) {
      case RailTab.overview:
        return OverviewView(
          ipc: _ipc,
          selectedDataset: _selectedDataset,
          onInvestigate: () => setState(() => _activeRailTab = RailTab.investigation),
          onViewReport: () => setState(() => _activeRailTab = RailTab.report),
          onSelectEquipment: (eq) => setState(() {
            _selectedEquipment = eq;
            _activeRailTab = RailTab.analysis;
          }),
          onSelectAnomaly: (id) => setState(() {
            _selectedAnomalyId = id;
            _activeRailTab = RailTab.investigation;
          }),
          onNavigateToData: () => setState(() => _activeRailTab = RailTab.data),
          onNavigateToBaseline: () => setState(() => _activeRailTab = RailTab.analysis),
          onNavigateToVisuals: () => setState(() => _activeRailTab = RailTab.visuals),
          onRunPipeline: _runPipeline,
          isPipelineRunning: _isPipelineRunning,
          pipelineStage: _pipelineStage,
          pipelineProgress: _pipelineProgress,
        );
      case RailTab.data:
        return DataView(ipc: _ipc, selectedDataset: _selectedDataset);
      case RailTab.analysis:
        return AnalysisView(
          ipc: _ipc,
          workspacePath: _workspacePath,
          selectedEquipment: _selectedEquipment,
          availableEquipment: _availableEquipment,
          onEquipmentChanged: (eq) => setState(() => _selectedEquipment = eq),
          onInvestigate: () => setState(() => _activeRailTab = RailTab.investigation),
          onViewVisuals: () => setState(() => _activeRailTab = RailTab.visuals),
        );
      case RailTab.investigation:
        return InvestigationView(
          ipc: _ipc,
          initialAnomalyId: _selectedAnomalyId,
          workspacePath: _workspacePath,
          onNavigateToBaseline: () => setState(() => _activeRailTab = RailTab.analysis),
          onNavigateToReport: () => setState(() => _activeRailTab = RailTab.report),
        );
      case RailTab.visuals:
        return VisualsView(ipc: _ipc, workspacePath: _workspacePath);
      case RailTab.report:
        return ReportView(ipc: _ipc, workspacePath: _workspacePath);
      case RailTab.browser:
        return BrowserSurface(ipc: _ipc);
      case RailTab.files:
      case RailTab.settings:
        return EditorSurface(
          activeFilePath: _activeFilePath,
          fileContent: _activeTabContent,
          openTabs: _openTabs,
          terminalLogs: _terminalLogs,
          onTerminalCommand: _onTerminalCommand,
          onSaveFile: _saveFile,
          onCloseTab: _closeTab,
          onTabSelected: (path) => setState(() => _activeFilePath = path),
        );
    }
  }

  String get _activeTabContent {
    final tab = _openTabs.where((t) => t.path == _activeFilePath).firstOrNull;
    return tab?.content ?? '';
  }

  @override
  void dispose() {
    for (final sub in _subscriptions) {
      sub.cancel();
    }
    _subscriptions.clear();
    _ipc.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      body: Column(
        children: [
          GlobalCommandBar(
            isConnected: _isConnected,
            workspacePath: _workspacePath,
            onRefresh: () => _ipc.connect(),
            port: _ipc.serverPort,
            selectedDataset: _selectedDataset,
            availableDatasets: _availableDatasets,
            onSelectDataset: _showDatasetSelectorDialog,
            selectedEquipment: _selectedEquipment,
            availableEquipment: _availableEquipment,
            onEquipmentSelected: (eq) => setState(() => _selectedEquipment = eq),
            isPipelineRunning: _isPipelineRunning,
            pipelineStage: _pipelineStage,
            pipelineProgress: _pipelineProgress,
            onRunPipeline: _runPipeline,
            isAgentPanelOpen: _isAgentPanelOpen,
            onToggleAgentPanel: () => setState(() => _isAgentPanelOpen = !_isAgentPanelOpen),
          ),
          Expanded(
            child: Row(
              children: [
                WorkspaceRail(
                  activeTab: _activeRailTab,
                  files: _files,
                  activeFilePath: _activeFilePath,
                  workspacePath: _workspacePath,
                  onFileSelected: _openFileInTab,
                  onTabChanged: (tab) => setState(() => _activeRailTab = tab),
                  onOpenFolder: _openFolder,
                  onNewFile: _newFile,
                  onNewFolder: () {},
                  onRefreshFiles: _loadFiles,
                  onDeleteFile: _deleteFile,
                  onRenameFile: _renameFile,
                  anomalyCount: _anomalyCount,
                ),
                Expanded(
                  child: _buildMainSurface(),
                ),
                if (_isAgentPanelOpen)
                  AgentPanel(
                    ipc: _ipc,
                    events: _events,
                    onOpenFile: _openFileInTab,
                    onRunCommand: _onTerminalCommand,
                    onClose: () => setState(() => _isAgentPanelOpen = false),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
