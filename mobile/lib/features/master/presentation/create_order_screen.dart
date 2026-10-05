import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/widgets/common.dart';
import '../../orders/application/orders_providers.dart';
import '../../orders/data/orders_repository.dart';
import '../../orders/domain/work_order.dart';
import '../../orders/presentation/order_detail_screen.dart';
import '../../references/data/references_repository.dart';
import 'board_screen.dart';

/// Выдача наряда «за минуту»: всё на одном экране, быстрые сроки, фото с камеры.
class CreateOrderScreen extends ConsumerStatefulWidget {
  const CreateOrderScreen({super.key});

  @override
  ConsumerState<CreateOrderScreen> createState() => _CreateOrderScreenState();
}

class _CreateOrderScreenState extends ConsumerState<CreateOrderScreen> {
  final _description = TextEditingController();
  final _photos = <XFile>[];
  OrderType _type = OrderType.planned;
  Priority _priority = Priority.medium;
  int? _workshopId;
  int? _equipmentId;
  int? _executorId;
  bool _stopped = false;
  DateTime _deadline = DateTime.now().add(const Duration(hours: 4));
  bool _sending = false;

  @override
  void dispose() {
    _description.dispose();
    super.dispose();
  }

  void _setType(OrderType t) => setState(() {
    _type = t;
    if (t == OrderType.emergency) {
      _priority = Priority.critical;
      _deadline = DateTime.now().add(const Duration(hours: 2));
      _stopped = true;
    }
  });

  Future<void> _pickDeadline() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _deadline,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_deadline),
    );
    if (time == null) return;
    setState(
      () => _deadline = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      ),
    );
  }

  Future<void> _submit() async {
    if (_description.text.trim().length < 5 ||
        _workshopId == null ||
        _executorId == null) {
      return showError(context, 'Заполните описание, участок и исполнителя');
    }
    setState(() => _sending = true);
    final repo = ref.read(ordersRepositoryProvider);
    try {
      final created = await repo.create(
        NewOrder(
          type: _type,
          description: _description.text.trim(),
          workshopId: _workshopId!,
          equipmentId: _equipmentId,
          executorId: _executorId,
          priority: _priority,
          deadline: _deadline,
          equipmentStopped: _stopped,
        ),
      );
      if (_photos.isNotEmpty) {
        await repo.uploadPhotos(created.order.id, after: false, files: _photos);
      }
      ref.invalidate(boardProvider);
      if (mounted) context.pushReplacement('/orders/${created.order.id}');
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final refs = ref.watch(referencesProvider);
    final executors = ref.watch(executorsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Новый наряд')),
      body: AsyncView(
        value: refs,
        data: (r) {
          final equipment = r.equipment
              .where((e) => e.workshopId == _workshopId)
              .toList();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              SegmentedButton<OrderType>(
                segments: [
                  for (final t in OrderType.values)
                    ButtonSegment(
                      value: t,
                      label: Text(t.label),
                      icon: Icon(
                        t == OrderType.emergency
                            ? Icons.warning_amber
                            : Icons.event,
                      ),
                    ),
                ],
                selected: {_type},
                onSelectionChanged: (s) => _setType(s.first),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _description,
                minLines: 2,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: 'Описание проблемы',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                initialValue: _workshopId,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Участок',
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final w in r.workshops)
                    DropdownMenuItem(value: w.id, child: Text(w.name)),
                ],
                onChanged: (v) => setState(() {
                  _workshopId = v;
                  _equipmentId = null;
                }),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                key: ValueKey(_workshopId),
                initialValue: _equipmentId,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Оборудование',
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final e in equipment)
                    DropdownMenuItem(
                      value: e.id,
                      child: Text('${e.name} (${e.code})'),
                    ),
                ],
                onChanged: (v) => setState(() => _equipmentId = v),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Оборудование остановлено'),
                value: _stopped,
                onChanged: (v) => setState(() => _stopped = v),
              ),
              AsyncView(
                value: executors,
                data: (list) => DropdownButtonFormField<int>(
                  initialValue: _executorId,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Исполнитель',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final e in list)
                      DropdownMenuItem(
                        value: e.id,
                        child: Row(
                          children: [
                            AvailabilityDot(e.availability),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                '${e.fio} · ${e.specialty ?? ''}',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                  onChanged: (v) => setState(() => _executorId = v),
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<Priority>(
                initialValue: _priority,
                decoration: const InputDecoration(
                  labelText: 'Приоритет',
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final p in Priority.values)
                    DropdownMenuItem(value: p, child: Text(p.label)),
                ],
                onChanged: (v) => setState(() => _priority = v!),
              ),
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.schedule),
                title: Text('Срок: ${dateTimeFmt.format(_deadline)}'),
                trailing: const Icon(Icons.edit_calendar),
                onTap: _pickDeadline,
              ),
              Wrap(
                spacing: 8,
                children: [
                  for (final h in const [1, 2, 4, 8])
                    ActionChip(
                      label: Text('+$h ч'),
                      onPressed: () => setState(
                        () =>
                            _deadline = DateTime.now().add(Duration(hours: h)),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                children: [
                  for (final p in _photos)
                    Chip(
                      label: Text(p.name),
                      onDeleted: () => setState(() => _photos.remove(p)),
                    ),
                  if (_photos.length < 5)
                    ActionChip(
                      avatar: const Icon(Icons.add_a_photo_outlined),
                      label: const Text('Фото «до»'),
                      onPressed: () async {
                        final f = await ImagePicker().pickImage(
                          source: ImageSource.camera,
                          maxWidth: 1920,
                          imageQuality: 85,
                        );
                        if (f != null) setState(() => _photos.add(f));
                      },
                    ),
                ],
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _sending ? null : _submit,
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                  backgroundColor: _type == OrderType.emergency
                      ? Colors.red
                      : null,
                ),
                child: Text(
                  _type == OrderType.emergency
                      ? 'Выдать аварийный наряд'
                      : 'Выдать наряд',
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
