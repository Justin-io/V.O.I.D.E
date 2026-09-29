import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/ipc_models.dart';


class EditorSurface extends StatefulWidget {
  final String activeFilePath;
  final String fileContent;
  final Function(String command)? onTerminalCommand;
  final List<String> terminalLogs;
  final List<EditorTab> openTabs;
  final Function(String path, String content)? onSaveFile;
  final Function(String path)? onCloseTab;
  final Function(String path)? onTabSelected;

  const EditorSurface({
    super.key,
    required this.activeFilePath,
    required this.fileContent,
    this.onTerminalCommand,
    this.terminalLogs = const [],
    this.openTabs = const [],
    this.onSaveFile,
    this.onCloseTab,
    this.onTabSelected,
  });

  @override
  State<EditorSurface> createState() => _EditorSurfaceState();
}

class _EditorSurfaceState extends State<EditorSurface> {
  bool _terminalOpen = true;
  final TextEditingController _terminalInputController = TextEditingController();
  final ScrollController _terminalScrollController = ScrollController();
  final ScrollController _editorScrollController = ScrollController();

  // Per-tab editors
  final Map<String, TextEditingController> _tabControllers = {};
  final Map<String, bool> _dirtyFlags = {};

  String get _activeTab => widget.activeFilePath;

  TextEditingController _getController(String path) {
    if (!_tabControllers.containsKey(path)) {
      _tabControllers[path] = TextEditingController(text: widget.fileContent);
      _tabControllers[path]!.addListener(() {
        if (mounted) setState(() => _dirtyFlags[path] = true);
      });
    }
    return _tabControllers[path]!;
  }

  @override
  void didUpdateWidget(EditorSurface old) {
    super.didUpdateWidget(old);
    // Sync content if the file was updated externally (e.g., AI write)
    if (widget.activeFilePath != old.activeFilePath || widget.fileContent != old.fileContent) {
      final path = widget.activeFilePath;
      if (path.isNotEmpty) {
        if (!_tabControllers.containsKey(path) || _tabControllers[path]!.text != widget.fileContent) {
          _tabControllers[path]?.dispose();
          _tabControllers[path] = TextEditingController(text: widget.fileContent);
          _tabControllers[path]!.addListener(() {
            if (mounted) setState(() => _dirtyFlags[path] = true);
          });
          _dirtyFlags[path] = false;
        }
      }
    }
    // Auto-scroll terminal on new logs
    if (widget.terminalLogs.length != old.terminalLogs.length) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_terminalScrollController.hasClients) {
          _terminalScrollController.animateTo(
            _terminalScrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 100),
            curve: Curves.easeOut,
          );
        }
      });
    }
  }

  @override
  void dispose() {
    for (final c in _tabControllers.values) {
      c.dispose();
    }
    _terminalInputController.dispose();
    _terminalScrollController.dispose();
    _editorScrollController.dispose();
    super.dispose();
  }

  void _saveCurrentFile() {
    if (_activeTab.isEmpty) return;
    final ctrl = _tabControllers[_activeTab];
    if (ctrl != null) {
      widget.onSaveFile?.call(_activeTab, ctrl.text);
      setState(() => _dirtyFlags[_activeTab] = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return KeyboardListener(
      focusNode: FocusNode(),
      onKeyEvent: (event) {
        if (event is KeyDownEvent &&
            event.logicalKey == LogicalKeyboardKey.keyS &&
            HardwareKeyboard.instance.isControlPressed) {
          _saveCurrentFile();
        }
      },
      child: Container(
        color: const Color(0xFF000000),
        child: Column(
          children: [
            // Tab bar
            _buildTabBar(),
            // Editor Area
            Expanded(
              flex: _terminalOpen ? 6 : 10,
              child: _buildEditorArea(),
            ),
            // Terminal
            if (_terminalOpen)
              Expanded(
                flex: 4,
                child: Container(
                  decoration: const BoxDecoration(
                    color: Color(0xFF050505),
                    border: Border(top: BorderSide(color: Color(0xFF1E1E1E))),
                  ),
                  child: _buildTerminalView(),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildTabBar() {
    final tabs = widget.openTabs;
    return Container(
      height: 34,
      color: const Color(0xFF0A0A0A),
      child: Row(
        children: [
          // Tabs list
          Expanded(
            child: tabs.isEmpty
                ? const SizedBox.shrink()
                : SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: tabs.map((tab) {
                        final isActive = tab.path == _activeTab;
                        final isDirty = _dirtyFlags[tab.path] ?? false;
                        return _buildTab(tab, isActive, isDirty);
                      }).toList(),
                    ),
                  ),
          ),
          // Right controls
          Row(
            children: [
              _tabBarButton(
                Icons.add,
                'New File',
                () {},
              ),
              _tabBarButton(
                _terminalOpen ? Icons.terminal : Icons.terminal_outlined,
                'Toggle Terminal',
                () => setState(() => _terminalOpen = !_terminalOpen),
                active: _terminalOpen,
              ),
              const SizedBox(width: 4),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTab(EditorTab tab, bool isActive, bool isDirty) {
    final filename = tab.path.split('/').last;
    return InkWell(
      onTap: () => widget.onTabSelected?.call(tab.path),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 180, minWidth: 80),
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xFF000000) : Colors.transparent,
          border: Border(
            top: BorderSide(
              color: isActive ? Colors.white : Colors.transparent,
              width: 1.5,
            ),
            right: const BorderSide(color: Color(0xFF1E1E1E)),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(_getFileIcon(filename), size: 11, color: isActive ? Colors.white : const Color(0xFF666666)),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                filename,
                style: TextStyle(
                  color: isActive ? Colors.white : const Color(0xFF888888),
                  fontSize: 11,
                  fontWeight: isActive ? FontWeight.w500 : FontWeight.normal,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 6),
            if (isDirty)
              Container(
                width: 6,
                height: 6,
                decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white),
              )
            else
              InkWell(
                onTap: () => widget.onCloseTab?.call(tab.path),
                child: const Icon(Icons.close, size: 11, color: Color(0xFF666666)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _tabBarButton(IconData icon, String tooltip, VoidCallback onTap, {bool active = false}) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          child: Icon(
            icon,
            size: 15,
            color: active ? Colors.white : const Color(0xFF666666),
          ),
        ),
      ),
    );
  }

  Widget _buildEditorArea() {
    if (_activeTab.isEmpty) {
      return _buildWelcomeScreen();
    }

    final ctrl = _getController(_activeTab);

    return Container(
      color: const Color(0xFF000000),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Line Numbers Gutter
          _buildLineNumbers(ctrl),
          // Code Editor
          Expanded(
            child: SingleChildScrollView(
              controller: _editorScrollController,
              child: TextField(
                controller: ctrl,
                maxLines: null,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 13,
                  color: Color(0xFFDCDCDC),
                  height: 1.5,
                ),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.all(14),
                  isDense: true,
                ),
                cursorColor: Colors.white,
                selectionControls: materialTextSelectionControls,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLineNumbers(TextEditingController ctrl) {
    // Recompute line count from controller
    return ValueListenableBuilder(
      valueListenable: ctrl,
      builder: (context, value, _) {
        final lines = ctrl.text.split('\n');
        return Container(
          width: 44,
          color: const Color(0xFF050505),
          padding: const EdgeInsets.only(top: 14, right: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: List.generate(
              lines.length,
              (i) => SizedBox(
                height: 19.5, // line height: 13 * 1.5
                child: Text(
                  '${i + 1}',
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 12,
                    color: Color(0xFF3A3A3A),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildWelcomeScreen() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFF252525), width: 1.5),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.code, size: 28, color: Color(0xFF333333)),
          ),
          const SizedBox(height: 16),
          const Text(
            'V.O.I.D.E. WORKSPACE',
            style: TextStyle(color: Color(0xFF555555), fontSize: 13, fontWeight: FontWeight.bold, letterSpacing: 1.5),
          ),
          const SizedBox(height: 8),
          const Text(
            'Open a file from the Explorer or ask the AI to generate code.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF3A3A3A), fontSize: 11),
          ),
          const SizedBox(height: 28),
          _shortcutHint('Ctrl+S', 'Save current file'),
          _shortcutHint('Ctrl+`', 'Toggle terminal'),
          _shortcutHint('Right-click file', 'Rename / Delete'),
        ],
      ),
    );
  }

  Widget _shortcutHint(String keys, String desc) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0xFF0F0F0F),
              borderRadius: BorderRadius.circular(3),
              border: Border.all(color: const Color(0xFF2A2A2A)),
            ),
            child: Text(keys, style: const TextStyle(color: Color(0xFF888888), fontSize: 10, fontFamily: 'monospace')),
          ),
          const SizedBox(width: 8),
          Text(desc, style: const TextStyle(color: Color(0xFF555555), fontSize: 10)),
        ],
      ),
    );
  }

  Widget _buildTerminalView() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Terminal Header with tabs
        Container(
          height: 28,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          color: const Color(0xFF0A0A0A),
          child: Row(
            children: [
              const Icon(Icons.terminal, size: 12, color: Colors.white),
              const SizedBox(width: 6),
              const Text(
                'TERMINAL',
                style: TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold, letterSpacing: 1),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Text(
                  '/bin/bash',
                  style: TextStyle(color: Color(0xFF555555), fontSize: 9, fontFamily: 'monospace'),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              InkWell(
                onTap: () => setState(() => _terminalOpen = false),
                child: const Icon(Icons.close, size: 13, color: Color(0xFF555555)),
              ),
            ],
          ),
        ),
        // Output
        Expanded(
          child: ListView.builder(
            controller: _terminalScrollController,
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            itemCount: widget.terminalLogs.length + 1,
            itemBuilder: (context, i) {
              if (i == 0) {
                return const Text(
                  '— V.O.I.D.E. PTY Session Active —',
                  style: TextStyle(color: Color(0xFF333333), fontSize: 10, fontFamily: 'monospace'),
                );
              }
              final log = widget.terminalLogs[i - 1];
              final isCmd = log.startsWith('\$');
              return SelectableText(
                log,
                style: TextStyle(
                  color: isCmd ? const Color(0xFF88FF88) : const Color(0xFFCCCCCC),
                  fontSize: 11,
                  fontFamily: 'monospace',
                  height: 1.45,
                ),
              );
            },
          ),
        ),
        // Input
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: const BoxDecoration(
            color: Color(0xFF060606),
            border: Border(top: BorderSide(color: Color(0xFF1A1A1A))),
          ),
          child: Row(
            children: [
              const Text(
                '\$ ',
                style: TextStyle(color: Color(0xFF88FF88), fontSize: 12, fontFamily: 'monospace', fontWeight: FontWeight.bold),
              ),
              Expanded(
                child: TextField(
                  controller: _terminalInputController,
                  style: const TextStyle(color: Colors.white, fontSize: 12, fontFamily: 'monospace'),
                  decoration: const InputDecoration(
                    border: InputBorder.none,
                    isDense: true,
                    contentPadding: EdgeInsets.zero,
                  ),
                  cursorColor: Colors.white,
                  onSubmitted: (val) {
                    if (val.trim().isNotEmpty) {
                      widget.onTerminalCommand?.call(val.trim());
                      _terminalInputController.clear();
                    }
                  },
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  IconData _getFileIcon(String filename) {
    if (filename.endsWith('.dart')) return Icons.code;
    if (filename.endsWith('.py')) return Icons.terminal;
    if (filename.endsWith('.js') || filename.endsWith('.ts')) return Icons.javascript;
    if (filename.endsWith('.json') || filename.endsWith('.toml') || filename.endsWith('.yaml')) return Icons.data_object;
    if (filename.endsWith('.md') || filename.endsWith('.txt')) return Icons.article_outlined;
    if (filename.endsWith('.html') || filename.endsWith('.css')) return Icons.web;
    if (filename.endsWith('.sh')) return Icons.terminal;
    return Icons.description_outlined;
  }
}
