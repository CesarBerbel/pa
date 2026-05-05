# Testes críticos adicionados

Foi adicionada a suite `appointments/tests/test_critical_architecture_regressions.py` para cobrir os fluxos de maior risco da refatoração arquitetural.

## Cobertura principal

- Disponibilidade de agenda:
  - exclusão de slots com marcações existentes;
  - exclusão de slots com bloqueios de agenda;
  - validação de horário fora do expediente;
  - validação de sobreposição entre marcações;
  - marcações canceladas não bloqueiam disponibilidade;
  - bloqueios recorrentes aplicam-se apenas ao dia correto.

- Criação de marcações:
  - criação via `AppointmentService`;
  - criação de log de auditoria;
  - envio de email de confirmação;
  - rejeição de double booking.

- Use cases:
  - confirmação de marcação;
  - conclusão apenas quando a marcação está confirmada.

- Selectors:
  - filtro por pesquisa, estado, serviço e lembrete enviado.

- Lembretes:
  - criação básica de `AppointmentReminderLog`.

## Comandos validados

```bash
SECRET_KEY=test-secret DEBUG=True python manage.py test appointments.tests.test_critical_architecture_regressions --verbosity 2
SECRET_KEY=test-secret DEBUG=True python manage.py test appointments.tests.test_critical_architecture_regressions appointments.tests.test_cancellation_flow appointments.tests.test_appointment_reminders --verbosity 1
```

Resultado: 23 testes passaram com sucesso.

A execução completa de `python manage.py test appointments` encontrou 103 testes e iniciou corretamente, mas excedeu o limite de execução do ambiente antes de concluir.
