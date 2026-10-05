import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config.dart';
import '../../auth/application/auth_controller.dart';

/// Администрирование (справочники, сотрудники) — в веб-панели. В мобильном
/// приложении только подсказка, куда идти.
class AdminScreen extends ConsumerWidget {
  const AdminScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      title: const Text('Администратор'),
      actions: [
        IconButton(
          icon: const Icon(Icons.logout),
          onPressed: () => ref.read(authControllerProvider.notifier).logout(),
        ),
      ],
    ),
    body: Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Ведение справочников и учётных записей доступно в веб-панели.\n\n'
          'API: ${AppConfig.apiUrl}/docs',
          textAlign: TextAlign.center,
        ),
      ),
    ),
  );
}
