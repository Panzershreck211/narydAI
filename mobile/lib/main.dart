import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app.dart';
import 'core/i18n/i18n.dart';
import 'core/notifications/local_notifications.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('ru');
  await loadLang();

  final container = ProviderContainer();
  await container.read(localNotificationsProvider).init();

  runApp(
    UncontrolledProviderScope(container: container, child: const NaryadApp()),
  );
}
