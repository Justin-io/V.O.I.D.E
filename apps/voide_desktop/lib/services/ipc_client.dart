import 'dart:async';
import 'dart:convert';
import 'dart:io';
import '../models/ipc_models.dart';

class IPCClient {
  final String uri;
  WebSocket? _socket;
  bool isConnected = false;
  int _msgId = 0;
  final Map<String, Completer<dynamic>> _pendingRequests = {};
  
  String? serverWorkspace;
  int? serverPort;
  String? serverVersion;

  final StreamController<AuditEvent> _eventStreamController = StreamController<AuditEvent>.broadcast();
  Stream<AuditEvent> get eventStream => _eventStreamController.stream;

  final StreamController<Map<String, dynamic>> _chatStreamController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get chatStream => _chatStreamController.stream;

  final StreamController<Map<String, dynamic>> _toolStreamController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get toolStream => _toolStreamController.stream;

  final StreamController<String> _workspaceStreamController = StreamController<String>.broadcast();
  Stream<String> get workspaceStream => _workspaceStreamController.stream;

  final StreamController<Map<String, dynamic>> _terminalStreamController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get terminalStream => _terminalStreamController.stream;

  final StreamController<bool> _connectionStreamController = StreamController<bool>.broadcast();
  Stream<bool> get connectionStream => _connectionStreamController.stream;

  final StreamController<Map<String, dynamic>> _helloStreamController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get helloStream => _helloStreamController.stream;

  final StreamController<Map<String, dynamic>> _pipelineStageStreamController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get pipelineStageStream => _pipelineStageStreamController.stream;

  Timer? _reconnectTimer;
  bool _isConnecting = false;
  bool _isDisposed = false;

  static String defaultUri() {
    final envPort = Platform.environment['VOIDE_IPC_PORT'];
    final port = (envPort != null && envPort.isNotEmpty) ? envPort : '8766';
    return 'ws://127.0.0.1:$port';
  }

  IPCClient({String? uri}) : uri = uri ?? defaultUri() {
    startAutoReconnect();
  }

  void startAutoReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!isConnected && !_isConnecting && !_isDisposed) {
        connect();
      }
    });
  }

  Future<void> connect() async {
    if (isConnected || _isConnecting || _isDisposed) return;
    _isConnecting = true;
    try {
      _socket = await WebSocket.connect(uri).timeout(const Duration(seconds: 3));

      isConnected = true;
      _connectionStreamController.add(true);

      _socket!.listen(
        _onMessage,
        onError: (err) {
          _cleanupConnection();
        },
        onDone: () {
          _cleanupConnection();
        },
      );
    } catch (e) {
      _cleanupConnection();
    } finally {
      _isConnecting = false;
    }
  }

  void _cleanupConnection() {
    isConnected = false;
    _connectionStreamController.add(false);
    // Reject any pending requests that were awaiting response
    for (final entry in _pendingRequests.entries) {
      if (!entry.value.isCompleted) {
        entry.value.completeError(StateError('IPC Connection closed while awaiting response.'));
      }
    }
    _pendingRequests.clear();
  }

  void _onMessage(dynamic raw) {
    try {
      final data = json.decode(raw as String) as Map<String, dynamic>;
      final type = data['type'] as String?;

      if (type == 'HELLO') {
        serverWorkspace = data['workspace'] as String?;
        serverVersion = data['version'] as String?;
        if (data['port'] != null) {
          serverPort = (data['port'] as num).toInt();
        }
        _helloStreamController.add(data);
      } else if (type == 'EVENT') {
        final eventJson = data['event'] as Map<String, dynamic>?;
        if (eventJson != null) {
          _eventStreamController.add(AuditEvent.fromJson(eventJson));
        }
      } else if (type == 'CHAT_STREAM') {
        _chatStreamController.add(data);
      } else if (type == 'TOOL_EXECUTED') {
        _toolStreamController.add(data);
      } else if (type == 'WORKSPACE_CHANGED') {
        final ws = data['workspace'] as String?;
        if (ws != null) {
          serverWorkspace = ws;
          _workspaceStreamController.add(ws);
        }
      } else if (type == 'TERMINAL_OUTPUT') {
        _terminalStreamController.add(data);
      } else if (type == 'DATA_PIPELINE_STAGE') {
        _pipelineStageStreamController.add(data);
      } else if (type == 'RESPONSE') {
        final id = data['id'] as String?;
        if (id != null && _pendingRequests.containsKey(id)) {
          final completer = _pendingRequests.remove(id)!;
          if (data['success'] == true) {
            completer.complete(data['result']);
          } else {
            completer.completeError(data['error'] ?? 'IPC error from V.O.I.D.E. server');
          }
        }
      }
    } catch (_) {}
  }

  Future<dynamic> send(String action, [Map<String, dynamic>? payload]) {
    final id = (++_msgId).toString();
    final completer = Completer<dynamic>();
    _pendingRequests[id] = completer;

    if (isConnected && _socket != null) {
      try {
        _socket!.add(json.encode({
          'action': action,
          'id': id,
          'payload': payload ?? {},
        }));
      } catch (e) {
        _pendingRequests.remove(id);
        completer.completeError(e);
      }
    } else {
      // Strictly NO mock fallback - real IPC only
      _pendingRequests.remove(id);
      completer.completeError(
        StateError('IPC Disconnected: Cannot communicate with V.O.I.D.E. runtime on $uri. Ensure backend is running.'),
      );
    }

    return completer.future;
  }

  void dispose() {
    _isDisposed = true;
    _reconnectTimer?.cancel();
    _socket?.close();
    _eventStreamController.close();
    _chatStreamController.close();
    _toolStreamController.close();
    _workspaceStreamController.close();
    _terminalStreamController.close();
    _connectionStreamController.close();
    _helloStreamController.close();
    _pipelineStageStreamController.close();
  }
}

