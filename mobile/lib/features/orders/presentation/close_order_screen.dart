import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../../core/i18n/i18n.dart';
import '../../../core/widgets/common.dart';
import '../../references/data/references_repository.dart';
import '../../references/domain/references.dart';
import '../application/orders_providers.dart';
import '../data/orders_repository.dart';
import '../domain/work_order.dart';

/// Форма закрытия наряда: отчёт (текст или голос), шифр неисправности,
/// списание материалов, фото «после» (обязательно для внеплановых).
class CloseOrderScreen extends ConsumerStatefulWidget {
  const CloseOrderScreen({super.key, required this.orderId});
  final int orderId;

  @override
  ConsumerState<CloseOrderScreen> createState() => _CloseOrderScreenState();
}

class _CloseOrderScreenState extends ConsumerState<CloseOrderScreen> {
  final _report = TextEditingController();
  final _speech = SpeechToText();

  /// Казахский — если телефон умеет его распознавать, иначе русский.
  Future<String> _speechLocale() async {
    if (currentLang == AppLang.kk) {
      final locales = await _speech.locales();
      final kk = locales.where(
        (l) => l.localeId.toLowerCase().startsWith('kk'),
      );
      if (kk.isNotEmpty) return kk.first.localeId;
    }
    return 'ru_RU';
  }

  final _materials = <MaterialLine>[];
  final _newPhotos = <XFile>[];
  RefItem? _fault;
  bool _listening = false;
  bool _sending = false;

  @override
  void dispose() {
    _speech.stop();
    _report.dispose();
    super.dispose();
  }

  Future<void> _toggleVoice() async {
    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      return;
    }
    final ok = await _speech.initialize(
      onStatus: (s) {
        if (s == 'done' || s == 'notListening') {
          setState(() => _listening = false);
        }
      },
    );
    if (!ok) {
      if (mounted) {
        showError(context, tr('Распознавание речи недоступно на устройстве'));
      }
      return;
    }
    final prefix = _report.text.isEmpty ? '' : '${_report.text.trimRight()} ';
    setState(() => _listening = true);
    await _speech.listen(
      listenOptions: SpeechListenOptions(
        localeId: await _speechLocale(),
        partialResults: true,
        listenMode: ListenMode.dictation,
      ),
      onResult: (r) =>
          setState(() => _report.text = prefix + r.recognizedWords),
    );
  }

  Future<void> _addMaterial(List<RefItem> catalog) async {
    final picked = await showModalBottomSheet<RefItem>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        builder: (_, scroll) => ListView(
          controller: scroll,
          children: [
            for (final m in catalog)
              ListTile(
                title: Text(m.name),
                subtitle: Text(m.unit ?? ''),
                onTap: () => Navigator.pop(ctx, m),
              ),
          ],
        ),
      ),
    );
    if (picked == null) return;
    setState(
      () => _materials.add(
        MaterialLine(
          materialId: picked.id,
          name: picked.name,
          unit: picked.unit ?? 'шт',
        ),
      ),
    );
  }

  Future<void> _takePhoto() async {
    final photo = await ImagePicker().pickImage(
      source: ImageSource.camera,
      maxWidth: 1920,
      imageQuality: 85,
    );
    if (photo != null) setState(() => _newPhotos.add(photo));
  }

  Future<void> _submit(OrderDetail detail) async {
    final hasAfter =
        detail.photos.any((p) => p.isAfter) || _newPhotos.isNotEmpty;
    String? error;
    if (_report.text.trim().split(RegExp(r'\s+')).length < 5) {
      error = tr('Опишите выполненные работы (не менее 5 слов)');
    } else if (_fault == null) {
      error = tr('Выберите шифр неисправности');
    } else if (detail.order.isEmergency && !hasAfter) {
      error = tr('Для внепланового наряда обязательно фото «после»');
    }
    if (error != null) return showError(context, error);

    setState(() => _sending = true);
    final repo = ref.read(ordersRepositoryProvider);
    try {
      if (_newPhotos.isNotEmpty) {
        await repo.uploadPhotos(widget.orderId, after: true, files: _newPhotos);
      }
      final result = await repo.complete(
        widget.orderId,
        report: _report.text.trim(),
        faultCodeId: _fault!.id,
        materials: _materials,
      );
      ref.invalidate(orderDetailProvider(widget.orderId));
      ref.invalidate(myOrdersProvider);
      if (!mounted) return;
      final ai = result.aiReport;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ai == null
                ? tr('Наряд исполнен')
                : tr('Наряд исполнен. ИИ-проверка: {verdictLabel}', {
                    'verdictLabel': ai.verdictLabel,
                  }),
          ),
          backgroundColor: ai?.color,
        ),
      );
      context.pop();
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(orderDetailProvider(widget.orderId));
    final refs = ref.watch(referencesProvider);

    return Scaffold(
      appBar: AppBar(title: Text(tr('Закрытие наряда'))),
      body: AsyncView(
        value: refs,
        data: (r) => AsyncView(
          value: detail,
          data: (d) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                d.order.description,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _report,
                minLines: 4,
                maxLines: 10,
                decoration: InputDecoration(
                  labelText: tr('Выполненные работы'),
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    tooltip: tr('Голосовой ввод'),
                    icon: Icon(
                      _listening ? Icons.stop_circle : Icons.mic,
                      color: _listening ? Colors.red : null,
                    ),
                    onPressed: _toggleVoice,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<RefItem>(
                initialValue: _fault,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: tr('Шифр неисправности'),
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final f in r.faultCodes)
                    DropdownMenuItem(value: f, child: Text(f.title)),
                ],
                onChanged: (v) => setState(() => _fault = v),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Text(
                    tr('Материалы и запчасти'),
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const Spacer(),
                  TextButton.icon(
                    onPressed: () => _addMaterial(r.materials),
                    icon: const Icon(Icons.add),
                    label: Text(tr('Добавить')),
                  ),
                ],
              ),
              for (final m in _materials)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(m.name),
                  trailing: SizedBox(
                    width: 150,
                    child: Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            initialValue: '${m.quantity}',
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true,
                            ),
                            decoration: InputDecoration(
                              suffixText: m.unit,
                              isDense: true,
                            ),
                            onChanged: (v) => m.quantity =
                                double.tryParse(v.replaceAll(',', '.')) ??
                                m.quantity,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => setState(() => _materials.remove(m)),
                        ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 16),
              Text(
                d.order.isEmergency
                    ? tr('Фото «после» (обязательно)')
                    : tr('Фото «после»'),
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final p in _newPhotos)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.file(
                        File(p.path),
                        width: 84,
                        height: 84,
                        fit: BoxFit.cover,
                      ),
                    ),
                  if (_newPhotos.length +
                          d.photos.where((p) => p.isAfter).length <
                      5)
                    OutlinedButton(
                      onPressed: _takePhoto,
                      style: OutlinedButton.styleFrom(
                        fixedSize: const Size(84, 84),
                        padding: EdgeInsets.zero,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: const Icon(Icons.add_a_photo_outlined),
                    ),
                ],
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _sending ? null : () => _submit(d),
                icon: _sending
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.task_alt),
                label: Text(tr('Исполнено')),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
