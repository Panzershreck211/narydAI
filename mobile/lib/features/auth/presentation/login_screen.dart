import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/api_error.dart';
import '../../../core/config.dart';
import '../../../core/i18n/i18n.dart';
import '../../../core/theme/app_theme.dart';
import '../application/auth_controller.dart';
import '../data/auth_repository.dart';

/// Вход: по ПИН-коду (рабочие на производстве) или по логину и паролю.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _login = TextEditingController();
  final _password = TextEditingController();
  final _pin = TextEditingController();
  final _server = TextEditingController();
  bool _pinMode = true;
  bool _serverEditing = false;
  bool _serverChecking = false;
  String? _serverError;

  @override
  void initState() {
    super.initState();
    ref.read(authRepositoryProvider).lastLogin().then((v) {
      if (v != null && mounted) _login.text = v;
    });
  }

  @override
  void dispose() {
    _login.dispose();
    _password.dispose();
    _pin.dispose();
    _server.dispose();
    super.dispose();
  }

  static bool _isNetworkError(Object? e) =>
      e is DioException &&
      e.response == null &&
      e.type != DioExceptionType.cancel &&
      e.type != DioExceptionType.badCertificate;

  void _editServer() => setState(() {
    _server.text = AppConfig.apiUrl;
    _serverError = null;
    _serverEditing = true;
  });

  /// Проверяет, что по адресу отвечает НарядAI, и только тогда сохраняет его.
  Future<void> _saveServer() async {
    final url = AppConfig.normalize(_server.text);
    if (url == null) {
      setState(() => _serverError = tr('Неверный адрес сервера'));
      return;
    }
    setState(() {
      _serverChecking = true;
      _serverError = null;
    });
    try {
      await Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 5),
        ),
      ).get('$url${AppConfig.apiPrefix}/setup/status');
      await AppConfig.saveServerUrl(url);
      ref.read(apiClientProvider).useCurrentServer();
      if (mounted) setState(() => _serverEditing = false);
    } catch (_) {
      if (mounted) {
        setState(
          () => _serverError = tr('Сервер не найден по адресу {url}', {
            'url': url,
          }),
        );
      }
    } finally {
      if (mounted) setState(() => _serverChecking = false);
    }
  }

  void _submit() {
    final auth = ref.read(authControllerProvider.notifier);
    if (_pinMode) {
      auth.pinLogin(_login.text, _pin.text);
    } else {
      auth.login(_login.text, _password.text);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authControllerProvider);
    final error = state.hasError ? ApiError.from(state.error!).message : null;
    // нет связи с сервером — сразу предлагаем проверить адрес
    ref.listen(authControllerProvider, (_, next) {
      if (next.hasError && _isNetworkError(next.error) && !_serverEditing) {
        _editServer();
      }
    });

    final c = context.colors;
    Widget label(String t) => Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(
        t,
        style: TextStyle(
          color: c.muted,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );

    return Scaffold(
      body: Container(
        // Фон как на странице входа панели: тёмный с синим свечением слева сверху
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: const Alignment(-0.6, -0.8),
            radius: 1.1,
            colors: [
              Color.alphaBlend(c.primary.withValues(alpha: 0.18), c.bg),
              c.bg,
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: c.surface,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: c.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Align(
                        alignment: Alignment.centerRight,
                        child: LangButton(),
                      ),
                      const SizedBox(height: 8),
                      BrandMark(
                        big: true,
                        subtitle: tr('Приложение исполнителя'),
                      ),
                      const SizedBox(height: 22),
                      SegmentedButton<bool>(
                        showSelectedIcon: false,
                        segments: [
                          ButtonSegment(
                            value: true,
                            label: Text(tr('ПИН-код')),
                            icon: Icon(Icons.pin_outlined, size: 18),
                          ),
                          ButtonSegment(
                            value: false,
                            label: Text(tr('Пароль')),
                            icon: Icon(Icons.password, size: 18),
                          ),
                        ],
                        selected: {_pinMode},
                        onSelectionChanged: (s) =>
                            setState(() => _pinMode = s.first),
                      ),
                      const SizedBox(height: 18),
                      label(_pinMode ? tr('Табельный номер') : tr('Логин')),
                      TextField(
                        controller: _login,
                        textInputAction: TextInputAction.next,
                      ),
                      const SizedBox(height: 14),
                      label(_pinMode ? tr('ПИН') : tr('Пароль')),
                      if (_pinMode)
                        TextField(
                          controller: _pin,
                          keyboardType: TextInputType.number,
                          obscureText: true,
                          maxLength: 6,
                          decoration: const InputDecoration(counterText: ''),
                          onSubmitted: (_) => _submit(),
                        )
                      else
                        TextField(
                          controller: _password,
                          obscureText: true,
                          onSubmitted: (_) => _submit(),
                        ),
                      if (error != null) ...[
                        const SizedBox(height: 14),
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: c.redSoft,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(error, style: TextStyle(color: c.red)),
                        ),
                      ],
                      const SizedBox(height: 18),
                      FilledButton(
                        onPressed: state.isLoading ? null : _submit,
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(48),
                        ),
                        child: state.isLoading
                            ? SizedBox.square(
                                dimension: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: c.primaryInk,
                                ),
                              )
                            : Text(tr('Войти')),
                      ),
                      const SizedBox(height: 14),
                      if (!_serverEditing)
                        Row(
                          children: [
                            Icon(Icons.dns_outlined, size: 16, color: c.muted),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                tr('Сервер: {url}', {'url': AppConfig.apiUrl}),
                                style: TextStyle(color: c.muted, fontSize: 12),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            TextButton(
                              onPressed: _editServer,
                              child: Text(tr('Изменить')),
                            ),
                          ],
                        )
                      else ...[
                        label(tr('Адрес сервера')),
                        TextField(
                          controller: _server,
                          keyboardType: TextInputType.url,
                          autocorrect: false,
                          decoration: InputDecoration(
                            hintText: '192.168.1.5',
                            helperText: tr(
                              'IP компьютера из окна запуска — порт 8080 подставится сам',
                            ),
                            helperMaxLines: 2,
                          ),
                          onSubmitted: (_) => _saveServer(),
                        ),
                        if (_serverError != null) ...[
                          const SizedBox(height: 8),
                          Text(_serverError!, style: TextStyle(color: c.red)),
                        ],
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton(
                                onPressed: _serverChecking
                                    ? null
                                    : () => setState(
                                        () => _serverEditing = false,
                                      ),
                                child: Text(tr('Отмена')),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: FilledButton.tonal(
                                onPressed: _serverChecking ? null : _saveServer,
                                child: _serverChecking
                                    ? const SizedBox.square(
                                        dimension: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : Text(tr('Проверить и сохранить')),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
