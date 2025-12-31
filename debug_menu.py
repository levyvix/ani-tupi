#!/usr/bin/env python3
"""Debug script to test InquirerPy rendering."""

import sys
from InquirerPy import inquirer

print("🔍 Testando InquirerPy...\n")

# Test 1: Fuzzy select
print("📝 Teste 1: Fuzzy select")
print("-" * 40)
try:
    options = ["Option 1", "Option 2", "Option 3"]
    result = inquirer.fuzzy(
        message="Escolha uma opção",
        choices=options,
        default=None,
        qmark="",
        amark="►",
        pointer="►",
        instruction="(Type to search, Q to quit)",
        mandatory=False,
        max_height="50%",
        raise_keyboard_interrupt=False,
    ).execute()
    print(f"✅ Fuzzy select funcionou! Selecionado: {result}")
except Exception as e:
    print(f"❌ Fuzzy select falhou: {e}")
    import traceback
    traceback.print_exc()

print("\n")

# Test 2: Simple select
print("📝 Teste 2: Simple select")
print("-" * 40)
try:
    options = ["Opção A", "Opção B", "Opção C"]
    result = inquirer.select(
        message="Escolha com setas",
        choices=options,
        default=None,
        qmark="",
        amark="►",
        pointer="►",
        instruction="(Use arrow keys, Q to quit)",
        mandatory=False,
        raise_keyboard_interrupt=False,
    ).execute()
    print(f"✅ Simple select funcionou! Selecionado: {result}")
except Exception as e:
    print(f"❌ Simple select falhou: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ Testes concluídos!")
