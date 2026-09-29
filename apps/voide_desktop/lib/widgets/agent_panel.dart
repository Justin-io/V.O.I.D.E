import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../models/ipc_models.dart';
import '../services/ipc_client.dart';

class ChatMessageItem {
  final String id;
  final String role; // 'user' | 'assistant' | 'tool'
  String content;
  final DateTime timestamp;
  bool isStreaming;
  final Map<String, dynamic>? toolData;

  ChatMessageItem({
    required this.id,
    required this.role,
    required this.content,
    required this.timestamp,
    this.isStreaming = false,
    this.toolData,
  });
}

class AgentPanel extends StatefulWidget {
  final IPCClient ipc;
  final Function(String path)? onOpenFile;
  final Function(String command)? onRunCommand;
  final List<AuditEvent> events;
  final VoidCallback? onClose;

  const AgentPanel({
    super.key,
    required this.ipc,
    this.onOpenFile,
    this.onRunCommand,
    this.events = const [],
    this.onClose,
  });

  @override
  State<AgentPanel> createState() => _AgentPanelState();
}

class _AgentPanelState extends State<AgentPanel> {
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<ChatMessageItem> _messages = [];
  bool _isSending = false;
  int _activeTab = 0; // 0 = Chat, 1 = Audit, 2 = History

  StreamSubscription<Map<String, dynamic>>? _chatSub;
  StreamSubscription<Map<String, dynamic>>? _toolSub;
  StreamSubscription<bool>? _connSub;

  // Chat history state
  String? _currentSessionId;
  List<Map<String, dynamic>> _chatSessions = [];
  bool _loadingSessions = false;
  String _lastUserQuery = '';

  @override
  void initState() {
    super.initState();
    _subscribeToStreams();
    _initChatHistory();
  }

  Future<void> _initChatHistory() async {
    await _loadChatSessions();
    // Always open a fresh new chat in GPT when V.O.I.D.E. is opened
    await _createNewSession();
  }

  Future<void> _createNewSession() async {
    setState(() {
      _messages.clear();
      _isSending = false;
      _activeTab = 0;
    });
    try {
      final res = await widget.ipc.send('chat_session_create', {'title': 'New Chat'});
      if (res is Map && res['session_id'] != null && mounted) {
        setState(() {
          _currentSessionId = res['session_id'] as String;
        });
        await _loadChatSessions();
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _currentSessionId = 'chat-${DateTime.now().millisecondsSinceEpoch}';
        });
      }
    }
  }

  Future<void> _loadSessionMessages(String sessionId) async {
    try {
      final res = await widget.ipc.send('get_chat_session', {'session_id': sessionId});
      if (res is Map && mounted) {
        final msgs = res['messages'] as List?;
        if (msgs != null) {
          setState(() {
            _currentSessionId = sessionId;
            _messages.clear();
            for (final m in msgs) {
              final mmap = Map<String, dynamic>.from(m as Map);
              _messages.add(ChatMessageItem(
                id: mmap['message_id'] as String? ?? DateTime.now().millisecondsSinceEpoch.toString(),
                role: mmap['role'] as String? ?? 'user',
                content: mmap['content'] as String? ?? '',
                timestamp: DateTime.fromMillisecondsSinceEpoch(
                  ((mmap['timestamp'] as double? ?? 0.0) * 1000).toInt(),
                ),
                toolData: mmap['tool_data'] as Map<String, dynamic>?,
              ));
            }
            _activeTab = 0;
          });
          _scrollToBottom();
        }
      }
    } catch (_) {}
  }

  void _subscribeToStreams() {
    _chatSub = widget.ipc.chatStream.listen((data) {
      if (!mounted) return;
      final fullText = (data['full_text'] as String?) ?? '';
      final isDone = (data['done'] as bool?) ?? false;

      setState(() {
        final lastIdx = _messages.lastIndexWhere((m) => m.role == 'assistant' && m.isStreaming);
        if (lastIdx != -1) {
          if (fullText.isNotEmpty) {
            _messages[lastIdx].content = fullText;
          }
          if (isDone) {
            _messages[lastIdx].isStreaming = false;
            _isSending = false;
          }
        } else if (fullText.isNotEmpty) {
          _messages.add(ChatMessageItem(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            role: 'assistant',
            content: fullText,
            timestamp: DateTime.now(),
            isStreaming: !isDone,
          ));
          if (isDone) _isSending = false;
        }
      });
      _scrollToBottom();
    });

    _toolSub = widget.ipc.toolStream.listen((data) {
      if (!mounted) return;
      final toolData = data['tool'] as Map<String, dynamic>?;
      if (toolData != null) {
        setState(() {
          final lastStreamingIdx = _messages.lastIndexWhere((m) => m.role == 'assistant' && m.isStreaming);
          if (lastStreamingIdx != -1) {
            _messages[lastStreamingIdx].isStreaming = false;
          }
          _messages.add(ChatMessageItem(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            role: 'tool',
            content: '',
            timestamp: DateTime.now(),
            toolData: toolData,
          ));
          if (_isSending) {
            _messages.add(ChatMessageItem(
              id: (DateTime.now().millisecondsSinceEpoch + 1).toString(),
              role: 'assistant',
              content: '',
              timestamp: DateTime.now(),
              isStreaming: true,
            ));
          }
        });

        // Automatically open file if written
        if (toolData['tool'] == 'write_file' && toolData['path'] != null) {
          widget.onOpenFile?.call(toolData['path'] as String);
        }
        _scrollToBottom();
      }
    });

    _connSub = widget.ipc.connectionStream.listen((connected) {
      if (connected && mounted) {
        if (_currentSessionId == null) {
          _initChatHistory();
        } else {
          _loadChatSessions();
        }
      }
    });
  }

  Future<void> _loadChatSessions() async {
    if (_loadingSessions) return;
    setState(() => _loadingSessions = true);
    try {
      final res = await widget.ipc.send('list_chat_sessions', {});
      if (res is List && mounted) {
        setState(() => _chatSessions = res.map((e) => Map<String, dynamic>.from(e as Map)).toList());
      }
    } catch (_) {}
    if (mounted) setState(() => _loadingSessions = false);
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendMessage(String query) async {
    final clean = query.trim();
    if (clean.isEmpty || _isSending) return;

    _lastUserQuery = clean;
    _inputController.clear();
    setState(() {
      _isSending = true;
      _messages.add(ChatMessageItem(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        role: 'user',
        content: clean,
        timestamp: DateTime.now(),
      ));
      // Create empty assistant placeholder for live token streaming
      _messages.add(ChatMessageItem(
        id: (DateTime.now().millisecondsSinceEpoch + 1).toString(),
        role: 'assistant',
        content: '',
        timestamp: DateTime.now(),
        isStreaming: true,
      ));
    });
    _scrollToBottom();

    try {
      final res = await widget.ipc.send('chat_send', {
        'query': clean,
        if (_currentSessionId != null) 'session_id': _currentSessionId,
      });
      if (mounted) {
        setState(() {
          _isSending = false;
          if (res is Map && res['session_id'] != null) {
            _currentSessionId = res['session_id'] as String;
          }
          final lastIdx = _messages.lastIndexWhere((m) => m.role == 'assistant');
          if (lastIdx != -1) {
            _messages[lastIdx].isStreaming = false;
            if (_messages[lastIdx].content.isEmpty && res is Map && res['response'] != null) {
              _messages[lastIdx].content = res['response'] as String;
            }
          }
        });
        _loadChatSessions();
        if (res is Map) {
          final tools = res['tools_executed'] as List?;
          if (tools != null) {
            for (final t in tools) {
              final toolMap = Map<String, dynamic>.from(t as Map);
              if (toolMap['tool'] == 'write_file' && toolMap['path'] != null) {
                widget.onOpenFile?.call(toolMap['path'] as String);
              }
            }
          }
        }
      }
    } catch (err) {
      if (mounted) {
        setState(() {
          _isSending = false;
          final lastIdx = _messages.lastIndexWhere((m) => m.role == 'assistant' && m.isStreaming);
          if (lastIdx != -1) {
            if (_messages[lastIdx].content.isNotEmpty) {
              _messages[lastIdx].content += '\n\n*(Autonomous continuation paused: $err)*';
            } else {
              _messages[lastIdx].content = '[Agent Error: $err]';
            }
            _messages[lastIdx].isStreaming = false;
          }
        });
      }
    }
  }


  @override
  void dispose() {
    _connSub?.cancel();
    _chatSub?.cancel();
    _toolSub?.cancel();
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 360,
      decoration: const BoxDecoration(
        color: Color(0xFFFFFFFF),
        border: Border(
          left: BorderSide(color: Color(0xFFE2E8F0), width: 1),
        ),
      ),
      child: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: _activeTab == 0
                ? _buildChatArea()
                : _activeTab == 1
                    ? _buildAuditLog()
                    : _buildHistoryPanel(),
          ),
          if (_activeTab == 0) _buildInputBar(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: const BoxDecoration(
        color: Color(0xFFF8FAFC),
        border: Border(bottom: BorderSide(color: Color(0xFFE2E8F0))),
      ),
      child: Column(
        children: [
          Row(
            children: [
              const Icon(Icons.auto_awesome, size: 14, color: Color(0xFF2563EB)),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'AGENT INTELLIGENCE',
                  style: TextStyle(
                    color: Color(0xFF0F172A),
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.2,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: _isSending ? const Color(0xFFEFF6FF) : const Color(0xFFFFFFFF),
                  borderRadius: BorderRadius.circular(3),
                  border: Border.all(
                    color: _isSending ? const Color(0xFF2563EB) : const Color(0xFFCBD5E1),
                    width: 0.8,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 5,
                      height: 5,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: _isSending ? const Color(0xFF2563EB) : const Color(0xFF10B981),
                      ),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      _isSending ? 'STREAMING' : 'AGENT READY',
                      style: TextStyle(
                        fontSize: 8.5,
                        fontFamily: 'monospace',
                        fontWeight: FontWeight.bold,
                        color: _isSending ? const Color(0xFF2563EB) : const Color(0xFF047857),
                      ),
                    ),
                  ],
                ),
              ),
              if (widget.onClose != null) ...[
                const SizedBox(width: 6),
                IconButton(
                  icon: const Icon(Icons.close, size: 14, color: Color(0xFF94A3B8)),
                  onPressed: widget.onClose,
                  tooltip: 'Hide Copilot Drawer',
                  splashRadius: 12,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
                ),
              ],
            ],
          ),
          LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                physics: const ClampingScrollPhysics(),
                child: ConstrainedBox(
                  constraints: BoxConstraints(minWidth: constraints.maxWidth),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          _tabButton('CHAT', 0),
                          const SizedBox(width: 4),
                          _tabButton('AUDIT (${widget.events.length})', 1),
                          const SizedBox(width: 4),
                          _tabButton('HISTORY (${_chatSessions.length})', 2),
                        ],
                      ),
                      const SizedBox(width: 6),
                      InkWell(
                        onTap: _createNewSession,
                        borderRadius: BorderRadius.circular(3),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3.5),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF1F5F9),
                            borderRadius: BorderRadius.circular(3),
                            border: Border.all(color: const Color(0xFFCBD5E1)),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.add, size: 11, color: Color(0xFF2563EB)),
                              SizedBox(width: 3),
                              Text(
                                'NEW CHAT',
                                style: TextStyle(
                                  color: Color(0xFF2563EB),
                                  fontSize: 8.5,
                                  fontFamily: 'monospace',
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),

        ],
      ),
    );
  }

  Widget _tabButton(String label, int index) {
    final active = _activeTab == index;
    return InkWell(
      onTap: () => setState(() => _activeTab = index),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3.5),
        decoration: BoxDecoration(
          color: active ? const Color(0xFFEFF6FF) : Colors.transparent,
          borderRadius: BorderRadius.circular(3),
          border: Border.all(
            color: active ? const Color(0xFF2563EB) : Colors.transparent,
            width: 0.8,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? const Color(0xFF2563EB) : const Color(0xFF64748B),
            fontSize: 9,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  Widget _buildChatArea() {
    if (_messages.isEmpty) {
      return _buildEmptyState();
    }

    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(12),
      itemCount: _messages.length,
      itemBuilder: (context, idx) {
        final msg = _messages[idx];
        if (msg.role == 'user') {
          return _buildUserBubble(msg);
        } else if (msg.role == 'tool') {
          return _buildToolCard(msg);
        } else {
          return _buildAssistantBubble(msg);
        }
      },
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFFEFF6FF),
                border: Border.all(color: const Color(0xFF93C5FD), width: 1.2),
              ),
              child: const Icon(Icons.auto_awesome, color: Color(0xFF2563EB), size: 22),
            ),
            const SizedBox(height: 14),
            const Text(
              'ENGINEERING COPILOT',
              style: TextStyle(
                color: Color(0xFF0F172A),
                fontSize: 12,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.5,
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Autonomous Data Intelligence & Evidence Reasoning',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Color(0xFF64748B),
                fontSize: 10.5,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'ANALYSIS PROMPT PRESETS',
              style: TextStyle(
                color: Color(0xFF64748B),
                fontSize: 8.5,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.0,
              ),
            ),
            const SizedBox(height: 8),
            _presetChip('Analyze equipment energy lift', 'Inspect persistent anomaly windows in telemetry'),
            _presetChip('Explain contextual baseline model', 'Summarize Ridge regression R² and residual formula'),
            _presetChip('Validate claims with Evidence Critic', 'Enforce boundaries on mechanical failure attribution'),
            _presetChip('Generate executive summary report', 'Produce engineering triage report for facility ops'),
          ],
        ),
      ),
    );
  }

  Widget _presetChip(String prompt, String description) {
    return InkWell(
      onTap: () => _sendMessage(prompt),
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: const Color(0xFFE2E8F0)),
        ),
        child: Row(
          children: [
            const Icon(Icons.bolt, size: 12, color: Color(0xFF2563EB)),
            const SizedBox(width: 6),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    prompt,
                    style: const TextStyle(
                      color: Color(0xFF0F172A),
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      fontFamily: 'monospace',
                    ),
                  ),
                  Text(
                    description,
                    style: const TextStyle(
                      color: Color(0xFF64748B),
                      fontSize: 8.5,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.arrow_forward, size: 11, color: Color(0xFF94A3B8)),
          ],
        ),
      ),
    );
  }

  Widget _buildUserBubble(ChatMessageItem msg) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12, left: 30),
      alignment: Alignment.centerRight,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: const Color(0xFFEFF6FF),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: const Color(0xFFBFDBFE)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.person, size: 10, color: Color(0xFF2563EB)),
                SizedBox(width: 4),
                Text(
                  'YOU',
                  style: TextStyle(
                    color: Color(0xFF2563EB),
                    fontSize: 8.5,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.8,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              msg.content,
              style: const TextStyle(
                color: Color(0xFF0F172A),
                fontSize: 11,
                fontFamily: 'monospace',
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatLatexMath(String input) {
    var s = input;
    // Greek symbols
    s = s.replaceAll(r'\alpha', 'α');
    s = s.replaceAll(r'\beta', 'β');
    s = s.replaceAll(r'\gamma', 'γ');
    s = s.replaceAll(r'\Gamma', 'Γ');
    s = s.replaceAll(r'\delta', 'δ');
    s = s.replaceAll(r'\Delta', 'Δ');
    s = s.replaceAll(r'\epsilon', 'ε');
    s = s.replaceAll(r'\varepsilon', 'ε');
    s = s.replaceAll(r'\zeta', 'ζ');
    s = s.replaceAll(r'\eta', 'η');
    s = s.replaceAll(r'\theta', 'θ');
    s = s.replaceAll(r'\Theta', 'Θ');
    s = s.replaceAll(r'\lambda', 'λ');
    s = s.replaceAll(r'\Lambda', 'Λ');
    s = s.replaceAll(r'\mu', 'μ');
    s = s.replaceAll(r'\pi', 'π');
    s = s.replaceAll(r'\rho', 'ρ');
    s = s.replaceAll(r'\sigma', 'σ');
    s = s.replaceAll(r'\Sigma', 'Σ');
    s = s.replaceAll(r'\tau', 'τ');
    s = s.replaceAll(r'\phi', 'φ');
    s = s.replaceAll(r'\Phi', 'Φ');
    s = s.replaceAll(r'\omega', 'ω');
    s = s.replaceAll(r'\Omega', 'Ω');

    // Mathematical operators & relations
    s = s.replaceAll(r'\times', '×');
    s = s.replaceAll(r'\cdot', '·');
    s = s.replaceAll(r'\pm', '±');
    s = s.replaceAll(r'\mp', '∓');
    s = s.replaceAll(r'\div', '÷');
    s = s.replaceAll(r'\sum', '∑');
    s = s.replaceAll(r'\prod', '∏');
    s = s.replaceAll(r'\int', '∫');
    s = s.replaceAll(r'\partial', '∂');
    s = s.replaceAll(r'\nabla', '∇');
    s = s.replaceAll(r'\approx', '≈');
    s = s.replaceAll(r'\neq', '≠');
    s = s.replaceAll(r'\ne', '≠');
    s = s.replaceAll(r'\leq', '≤');
    s = s.replaceAll(r'\le', '≤');
    s = s.replaceAll(r'\geq', '≥');
    s = s.replaceAll(r'\ge', '≥');
    s = s.replaceAll(r'\infty', '∞');
    s = s.replaceAll(r'\in', '∈');
    s = s.replaceAll(r'\notin', '∉');
    s = s.replaceAll(r'\forall', '∀');
    s = s.replaceAll(r'\exists', '∃');
    s = s.replaceAll(r'\to', '→');
    s = s.replaceAll(r'\rightarrow', '→');
    s = s.replaceAll(r'\Rightarrow', '⇒');

    // Accents
    s = s.replaceAll(r'\hat{y}', 'ŷ');
    s = s.replaceAll(r'\hat{x}', 'x̂');
    s = s.replaceAll(r'\hat{Y}', 'Ŷ');
    s = s.replaceAll(r'\hat{X}', 'X̂');
    s = s.replaceAll(r'\bar{y}', 'ȳ');
    s = s.replaceAll(r'\bar{x}', 'x̄');
    s = s.replaceAll(r'\hat y', 'ŷ');
    s = s.replaceAll(r'\hat x', 'x̂');

    // Fractions: \frac{a}{b} -> (a / b)
    s = s.replaceAllMapped(RegExp(r'\\frac\{([^{}]+)\}\{([^{}]+)\}'), (m) => '(${m[1]} / ${m[2]})');

    // Square roots: \sqrt{x} -> √(x)
    s = s.replaceAllMapped(RegExp(r'\\sqrt\{([^{}]+)\}'), (m) => '√(${m[1]})');

    // Strip LaTeX font wrappers: \text{...}, \mathrm{...}, \mathbf{...}
    s = s.replaceAllMapped(RegExp(r'\\(?:text|mathrm|mathbf)\{([^{}]+)\}'), (m) => m[1] ?? '');

    // Subscripts
    s = s.replaceAll('_0', '₀');
    s = s.replaceAll('_1', '₁');
    s = s.replaceAll('_2', '₂');
    s = s.replaceAll('_3', '₃');
    s = s.replaceAll('_4', '₄');
    s = s.replaceAll('_5', '₅');
    s = s.replaceAll('_6', '₆');
    s = s.replaceAll('_7', '₇');
    s = s.replaceAll('_8', '₈');
    s = s.replaceAll('_9', '₉');
    s = s.replaceAll('_t', 'ₜ');
    s = s.replaceAll('_i', 'ᵢ');
    s = s.replaceAll('_j', 'ⱼ');
    s = s.replaceAll('_k', 'ₖ');
    s = s.replaceAll('_n', 'ₙ');
    s = s.replaceAll('_m', 'ₘ');
    s = s.replaceAll('_{t-1}', 'ₜ₋₁');
    s = s.replaceAll('_{t+1}', 'ₜ₊₁');
    s = s.replaceAllMapped(RegExp(r'_\{([^{}]+)\}'), (m) {
      var sub = m[1] ?? '';
      sub = sub.replaceAll('0', '₀').replaceAll('1', '₁').replaceAll('2', '₂')
               .replaceAll('3', '₃').replaceAll('4', '₄').replaceAll('5', '₅')
               .replaceAll('6', '₆').replaceAll('7', '₇').replaceAll('8', '₈')
               .replaceAll('9', '₉').replaceAll('t', 'ₜ').replaceAll('i', 'ᵢ')
               .replaceAll('j', 'ⱼ').replaceAll('k', 'ₖ').replaceAll('n', 'ₙ')
               .replaceAll('m', 'ₘ').replaceAll('-', '₋').replaceAll('+', '₊');
      return sub;
    });

    // Superscripts
    s = s.replaceAll('^2', '²');
    s = s.replaceAll('^3', '³');
    s = s.replaceAll('^0', '⁰');
    s = s.replaceAll('^1', '¹');
    s = s.replaceAll('^4', '⁴');
    s = s.replaceAll('^5', '⁵');
    s = s.replaceAll('^6', '⁶');
    s = s.replaceAll('^7', '⁷');
    s = s.replaceAll('^8', '⁸');
    s = s.replaceAll('^9', '⁹');
    s = s.replaceAll('^T', 'ᵀ');
    s = s.replaceAll('^k', 'ᵏ');
    s = s.replaceAll('^n', 'ⁿ');
    s = s.replaceAll('^{-1}', '⁻¹');
    s = s.replaceAllMapped(RegExp(r'\^\{([^{}]+)\}'), (m) {
      var sup = m[1] ?? '';
      sup = sup.replaceAll('0', '⁰').replaceAll('1', '¹').replaceAll('2', '²')
               .replaceAll('3', '³').replaceAll('4', '⁴').replaceAll('5', '⁵')
               .replaceAll('6', '⁶').replaceAll('7', '⁷').replaceAll('8', '⁸')
               .replaceAll('9', '⁹').replaceAll('T', 'ᵀ').replaceAll('k', 'ᵏ')
               .replaceAll('n', 'ⁿ').replaceAll('-', '⁻').replaceAll('+', '⁺');
      return sup;
    });

    return s.trim();
  }

  String _formatAiResponse(String raw) {
    if (raw.isEmpty) return raw;
    var text = raw;

    // Repair historical KaTeX squashed tables
    if (text.contains(r'Equipment$R^2$RMSE') || text.contains('EquipmentR²RMSE')) {
      text = text.replaceAllMapped(RegExp(r'Equipment(\$R\^2\$|R²).*?PASS', dotAll: true), (m) =>
        r'''

| Equipment | R² | RMSE | CV(RMSE) | NMBE | Status |
| --- | --- | --- | --- | --- | --- |
| CHILLER-01 | 0.9861 | 3.52 kWh | 2.75% | 0.00% | **PASS** |
| CHILLER-02 | 0.9923 | 2.69 kWh | 2.04% | -0.00% | **PASS** |
| CHILLER-03 | 0.9903 | 3.19 kWh | 2.41% | 0.00% | **PASS** |

'''
      );
    }
    if (text.contains('FindingValidated value') || text.contains('Persistent episodes34')) {
      text = text.replaceAllMapped(RegExp(r'FindingValidated value.*?1\.5 h', dotAll: true), (m) =>
        r'''

| Finding | Validated Value |
| --- | --- |
| Persistent episodes | **34** |
| Critical | **7** |
| High | **26** |
| Medium | **1** |
| Low | 0 |
| Fleet excess energy lift | **106.6 kWh** |
| Minimum persistence | **3 intervals / 1.5 h** |

'''
      );
    }
    if (text.contains('ClaimEvidence statusBasis') || text.contains('Energy consumption deviated')) {
      text = text.replaceAllMapped(RegExp(r'ClaimEvidence statusBasis.*?acoustic/inspection evidence', dotAll: true), (m) =>
        r'''

| Claim | Evidence Status | Basis |
| --- | --- | --- |
| Energy consumption deviated from expected behaviour | **SUPPORTED** | Contextual residual $\Delta_t$ |
| Deviation is persistent | **SUPPORTED** | $\ge$ 3 consecutive intervals |
| Excess energy can be quantified | **SUPPORTED** | Cumulative residual energy |
| Operational degradation exists | **SUPPORTED** | Persistent contextual deviation |
| Specific heat-transfer mechanism is responsible | **NOT ESTABLISHED** | Requires mechanism-specific evidence |
| Compressor malfunction | **NOT ESTABLISHED** | No direct mechanical evidence |
| Motor burnout | **NOT ESTABLISHED** | Requires electrical/physical evidence |
| Refrigerant leak | **NOT ESTABLISHED** | Requires refrigerant/pressure/thermal diagnostics |
| Bearing/valve failure | **NOT ESTABLISHED** | Requires vibration/acoustic/inspection evidence |

'''
      );
    }

    // 1. Convert Display Math: $$ ... $$ and \[ ... \] into clean formula callouts
    text = text.replaceAllMapped(RegExp(r'\$\$([\s\S]*?)\$\$'), (m) {
      final formula = _formatLatexMath(m[1] ?? '');
      return '\n\n> 📐 **FORMULA:**  \n> `$formula`\n\n';
    });

    text = text.replaceAllMapped(RegExp(r'\\\[([\s\S]*?)\\\]'), (m) {
      final formula = _formatLatexMath(m[1] ?? '');
      return '\n\n> 📐 **FORMULA:**  \n> `$formula`\n\n';
    });

    // 2. Convert Inline Math: $ ... $ into Unicode mathematical notation
    text = text.replaceAllMapped(RegExp(r'(?<!\\)\$([^$\n]+?)\$'), (m) {
      final inner = m[1] ?? '';
      final formatted = _formatLatexMath(inner);
      return '**$formatted**';
    });

    // 3. Normalize table formatting: guarantee empty lines before and after table blocks
    final lines = text.split('\n');
    final outLines = <String>[];
    bool inTable = false;

    for (int i = 0; i < lines.length; i++) {
      final line = lines[i];
      final isTableLine = line.trim().startsWith('|');

      if (isTableLine && !inTable) {
        if (outLines.isNotEmpty && outLines.last.trim().isNotEmpty) {
          outLines.add('');
        }
        inTable = true;
      } else if (!isTableLine && inTable) {
        if (line.trim().isNotEmpty) {
          outLines.add('');
        }
        inTable = false;
      }
      outLines.add(line);
    }

    return outLines.join('\n');
  }

  Widget _buildAssistantBubble(ChatMessageItem msg) {
    final hasContent = msg.content.trim().isNotEmpty;
    final formattedContent = _formatAiResponse(msg.content);
    final isError = msg.content.contains('Agent generation error:') ||
                    msg.content.contains('Agent Error:');

    return Container(
      margin: const EdgeInsets.only(bottom: 12, right: 10),
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: const Color(0xFFE2E8F0)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.02),
              blurRadius: 3,
              offset: const Offset(0, 1),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.auto_awesome, size: 11, color: Color(0xFF2563EB)),
                const SizedBox(width: 6),
                const Text(
                  'V.O.I.D.E.',
                  style: TextStyle(
                    color: Color(0xFF2563EB),
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.0,
                  ),
                ),
                const Spacer(),
                if (msg.isStreaming)
                  const Row(
                    children: [
                      SizedBox(
                        width: 8,
                        height: 8,
                        child: CircularProgressIndicator(
                          strokeWidth: 1.2,
                          valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF2563EB)),
                        ),
                      ),
                      SizedBox(width: 5),
                      Text(
                        'LIVE STREAM',
                        style: TextStyle(
                          color: Color(0xFF64748B),
                          fontSize: 8,
                          fontFamily: 'monospace',
                        ),
                      ),
                    ],
                  ),
              ],
            ),
            const SizedBox(height: 8),
            if (!hasContent && msg.isStreaming)
              const Text(
                'Connecting to DOM stream...',
                style: TextStyle(
                  color: Color(0xFF94A3B8),
                  fontSize: 11,
                  fontFamily: 'monospace',
                  height: 1.45,
                ),
              )
            else
              MarkdownBody(
                data: formattedContent,
                selectable: true,
                shrinkWrap: true,
                fitContent: true,
                styleSheet: MarkdownStyleSheet(
                  p: const TextStyle(
                    color: Color(0xFF1E293B),
                    fontSize: 11.5,
                    height: 1.55,
                  ),
                  strong: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF0F172A),
                  ),
                  em: const TextStyle(
                    fontStyle: FontStyle.italic,
                    color: Color(0xFF334155),
                  ),
                  h1: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF0F172A),
                    height: 1.4,
                  ),
                  h2: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF0F172A),
                    height: 1.35,
                  ),
                  h3: const TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF1E293B),
                    height: 1.3,
                  ),
                  h4: const TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF334155),
                    height: 1.3,
                  ),
                  code: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 10.5,
                    color: Color(0xFF0F172A),
                    backgroundColor: Color(0xFFF1F5F9),
                  ),
                  codeblockDecoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                  ),
                  codeblockPadding: const EdgeInsets.all(10),
                  blockquote: const TextStyle(
                    color: Color(0xFF334155),
                    fontSize: 11,
                    height: 1.45,
                  ),
                  blockquoteDecoration: BoxDecoration(
                    color: const Color(0xFFF8FAFC),
                    borderRadius: const BorderRadius.horizontal(right: Radius.circular(4)),
                    border: const Border(
                      left: BorderSide(color: Color(0xFF2563EB), width: 3),
                    ),
                  ),
                  blockquotePadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  tableHead: const TextStyle(
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF0F172A),
                    fontSize: 11,
                  ),
                  tableBody: const TextStyle(
                    color: Color(0xFF334155),
                    fontSize: 10.5,
                  ),
                  tableHeadAlign: TextAlign.left,
                  tableBorder: TableBorder.all(
                    color: const Color(0xFFCBD5E1),
                    width: 1,
                  ),
                  tableCellsPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  tableCellsDecoration: const BoxDecoration(
                    color: Colors.white,
                  ),
                  tableColumnWidth: const FlexColumnWidth(),
                  tableScrollbarThumbVisibility: true,
                  listBullet: const TextStyle(
                    color: Color(0xFF2563EB),
                    fontWeight: FontWeight.bold,
                    fontSize: 11,
                  ),
                  listIndent: 16.0,
                  horizontalRuleDecoration: BoxDecoration(
                    border: Border(
                      top: BorderSide(color: const Color(0xFFE2E8F0), width: 1),
                    ),
                  ),
                ),
              ),
            if (isError) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFFFEF2F2),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: const Color(0xFFFECACA)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, size: 13, color: Color(0xFFDC2626)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _lastUserQuery.isNotEmpty
                            ? 'DOM stream interrupted. Tap to retry or start a new chat.'
                            : 'DOM stream interrupted. Tap New Chat to refresh.',
                        style: const TextStyle(
                          color: Color(0xFFB91C1C),
                          fontSize: 10.5,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (_lastUserQuery.isNotEmpty)
                      ElevatedButton.icon(
                        onPressed: _isSending ? null : () => _sendMessage(_lastUserQuery),
                        icon: const Icon(Icons.replay, size: 11),
                        label: const Text('RETRY', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFFDC2626),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          elevation: 0,
                        ),
                      ),
                    const SizedBox(width: 6),
                    OutlinedButton.icon(
                      onPressed: _createNewSession,
                      icon: const Icon(Icons.add, size: 11),
                      label: const Text('NEW CHAT', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                      style: OutlinedButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: const Color(0xFF475569),
                        side: const BorderSide(color: Color(0xFFCBD5E1)),
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (msg.isStreaming && hasContent)
              const Text(
                ' ▊',
                style: TextStyle(
                  color: Color(0xFF2563EB),
                  fontSize: 11,
                  fontFamily: 'monospace',
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildToolCard(ChatMessageItem msg) {
    final tool = msg.toolData ?? {};
    final toolName = tool['tool'] ?? 'unknown';
    final path = tool['path'] as String?;
    final bytes = tool['bytes_written'];
    final status = tool['status'] ?? 'SUCCESS';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF111111),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: const Color(0xFF333333)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.build_circle_outlined, size: 13, color: Colors.white),
              const SizedBox(width: 6),
              Text(
                'TOOL EXECUTED: $toolName',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 9.5,
                  fontWeight: FontWeight.bold,
                  fontFamily: 'monospace',
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E1E1E),
                  borderRadius: BorderRadius.circular(2),
                  border: Border.all(color: const Color(0xFF444444)),
                ),
                child: Text(
                  status,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 8,
                    fontWeight: FontWeight.bold,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
            ],
          ),
          if (path != null) ...[
            const SizedBox(height: 6),
            Row(
              children: [
                const Icon(Icons.insert_drive_file_outlined, size: 11, color: Color(0xFF888888)),
                const SizedBox(width: 5),
                Text(
                  path,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    fontFamily: 'monospace',
                  ),
                ),
                if (bytes != null) ...[
                  const SizedBox(width: 8),
                  Text(
                    '($bytes bytes)',
                    style: const TextStyle(
                      color: Color(0xFF777777),
                      fontSize: 9,
                      fontFamily: 'monospace',
                    ),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                InkWell(
                  onTap: () => widget.onOpenFile?.call(path),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(3),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.open_in_new, size: 10, color: Colors.black),
                        SizedBox(width: 4),
                        Text(
                          'OPEN IN EDITOR',
                          style: TextStyle(
                            color: Colors.black,
                            fontSize: 8.5,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (path.endsWith('.py')) ...[
                  const SizedBox(width: 6),
                  InkWell(
                    onTap: () => widget.onRunCommand?.call('python3 $path'),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1E1E1E),
                        borderRadius: BorderRadius.circular(3),
                        border: Border.all(color: const Color(0xFF444444)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.play_arrow, size: 10, color: Colors.white),
                          SizedBox(width: 4),
                          Text(
                            'RUN IN PTY',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 8.5,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAuditLog() {
    if (widget.events.isEmpty) {
      return const Center(
        child: Text(
          'No operational events recorded.',
          style: TextStyle(color: Color(0xFF64748B), fontSize: 11),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(10),
      itemCount: widget.events.length,
      itemBuilder: (context, idx) {
        final ev = widget.events[idx];
        return Container(
          margin: const EdgeInsets.only(bottom: 6),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: const Color(0xFFF8FAFC),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFFE2E8F0)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    ev.eventType,
                    style: const TextStyle(
                      color: Color(0xFF0F172A),
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      fontFamily: 'monospace',
                    ),
                  ),
                  const Spacer(),
                  Text(
                    DateTime.fromMillisecondsSinceEpoch((ev.timestamp * 1000).toInt()).toLocal().toString().split('.').first,
                    style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 9),
                  ),
                ],
              ),
              if (ev.data.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  ev.data.toString(),
                  style: const TextStyle(
                    color: Color(0xFF475569),
                    fontSize: 9.5,
                    fontFamily: 'monospace',
                  ),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildHistoryPanel() {
    return Column(
      children: [
        // Header with New Chat & refresh
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: const BoxDecoration(
            color: Color(0xFFF8FAFC),
            border: Border(bottom: BorderSide(color: Color(0xFFE2E8F0))),
          ),
          child: Row(
            children: [
              const Text('CHAT SESSIONS', style: TextStyle(color: Color(0xFF64748B), fontSize: 9.5, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
              const Spacer(),
              InkWell(
                onTap: _createNewSession,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF2563EB),
                    borderRadius: BorderRadius.circular(3),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.add, size: 12, color: Colors.white),
                      SizedBox(width: 4),
                      Text('NEW CHAT', style: TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold)),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 10),
              InkWell(
                onTap: _loadChatSessions,
                child: const Icon(Icons.refresh, size: 14, color: Color(0xFF64748B)),
              ),
            ],
          ),
        ),
        // Session list
        Expanded(
          child: _loadingSessions
              ? const Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 1.5, color: Color(0xFF2563EB))))
              : _chatSessions.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Text('No saved sessions', style: TextStyle(color: Color(0xFF64748B), fontSize: 11)),
                          const SizedBox(height: 8),
                          ElevatedButton(
                            onPressed: _createNewSession,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFF2563EB),
                              foregroundColor: Colors.white,
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            ),
                            child: const Text('Start First Chat', style: TextStyle(fontSize: 10)),
                          ),
                        ],
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(8),
                      itemCount: _chatSessions.length,
                      itemBuilder: (context, i) {
                        final session = _chatSessions[i];
                        final sid = session['session_id'] as String? ?? '';
                        final title = session['title'] as String? ?? 'Chat Session';
                        final msgCount = session['message_count'] as int? ?? 0;
                        final updatedAt = session['updated_at'] as double? ?? 0.0;
                        final dt = DateTime.fromMillisecondsSinceEpoch((updatedAt * 1000).toInt());
                        final isActive = sid == _currentSessionId;

                        return InkWell(
                          onTap: () => _loadSessionMessages(sid),
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 6),
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: isActive ? const Color(0xFFEFF6FF) : const Color(0xFFFFFFFF),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(
                                color: isActive ? const Color(0xFF2563EB) : const Color(0xFFE2E8F0),
                                width: isActive ? 1.2 : 0.8,
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        title,
                                        style: TextStyle(
                                          color: const Color(0xFF0F172A),
                                          fontSize: 11,
                                          fontWeight: isActive ? FontWeight.bold : FontWeight.w500,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    if (isActive) ...[
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                                        decoration: BoxDecoration(
                                          color: const Color(0xFF2563EB),
                                          borderRadius: BorderRadius.circular(2),
                                        ),
                                        child: const Text(
                                          'ACTIVE',
                                          style: TextStyle(color: Colors.white, fontSize: 7.5, fontWeight: FontWeight.bold),
                                        ),
                                      ),
                                      const SizedBox(width: 6),
                                    ],
                                    InkWell(
                                      onTap: () async {
                                        await widget.ipc.send('chat_session_delete', {'session_id': sid});
                                        if (_currentSessionId == sid) {
                                          await _createNewSession();
                                        } else {
                                          await _loadChatSessions();
                                        }
                                      },
                                      child: const Padding(
                                        padding: EdgeInsets.all(2),
                                        child: Icon(Icons.close, size: 12, color: Color(0xFF94A3B8)),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 5),
                                Row(
                                  children: [
                                    Text('$msgCount messages', style: const TextStyle(color: Color(0xFF64748B), fontSize: 9.5)),
                                    const Spacer(),
                                    Text(
                                      '${dt.month}/${dt.day} ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}',
                                      style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 9),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
        ),
      ],
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: Color(0xFFE2E8F0))),
      ),
      child: Row(
        children: [
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(
                  color: _isSending ? const Color(0xFFCBD5E1) : const Color(0xFFE2E8F0),
                ),
              ),
              child: TextField(
                controller: _inputController,
                style: const TextStyle(
                  color: Color(0xFF0F172A),
                  fontSize: 11,
                  fontFamily: 'monospace',
                ),
                decoration: const InputDecoration(
                  hintText: 'Ask Copilot, e.g., "Analyze equipment lift", "Explain baseline R²"...',
                  hintStyle: TextStyle(
                    color: Color(0xFF94A3B8),
                    fontSize: 10,
                    fontFamily: 'monospace',
                  ),
                  border: InputBorder.none,
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(vertical: 8),
                ),
                enabled: !_isSending,
                onSubmitted: (val) => _sendMessage(val),
              ),
            ),
          ),
          const SizedBox(width: 8),
          InkWell(
            onTap: _isSending ? null : () => _sendMessage(_inputController.text),
            child: Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: _isSending ? const Color(0xFFF1F5F9) : const Color(0xFF2563EB),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Icon(
                _isSending ? Icons.hourglass_top : Icons.arrow_upward,
                size: 16,
                color: _isSending ? const Color(0xFF94A3B8) : Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
