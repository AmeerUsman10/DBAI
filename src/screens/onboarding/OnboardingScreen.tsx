import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, Alert, Image
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { colors, spacing, radius, minTapTarget } from '../../theme/colors';
import { saveBarber, saveAvailability, createService } from '../../database/db';
import { signInAnonymously } from '../../database/sync';
import { useStore } from '../../store/useStore';
import { CURRENCIES } from '../../lib/currency';
import type { Currency } from '../../types';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

type Step = 'profile' | 'hours' | 'services';

export function OnboardingScreen({ onComplete }: { onComplete: () => void }) {
  const setBarber = useStore((s) => s.setBarber);
  const setServices = useStore((s) => s.setServices);
  const setCurrency = useStore((s) => s.setCurrency);

  const [step, setStep] = useState<Step>('profile');

  // Profile
  const [name, setName] = useState('');
  const [shopName, setShopName] = useState('');
  const [phone, setPhone] = useState('');
  const [photoUri, setPhotoUri] = useState<string | undefined>();
  const [currency, setCurrencyLocal] = useState<Currency>('PKR');

  // Hours
  const [activeDays, setActiveDays] = useState<boolean[]>([false, true, true, true, true, true, false]);
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('18:00');

  // Services
  const [services, setServicesList] = useState([{ name: '', price: '' }]);

  async function pickPhoto() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.8,
    });
    if (!result.canceled) setPhotoUri(result.assets[0].uri);
  }

  function goProfile() {
    if (!name.trim() || !shopName.trim() || !phone.trim()) {
      Alert.alert('Required', 'Please fill in your name, shop name, and phone number.');
      return;
    }
    setStep('hours');
  }

  function goServices() {
    if (!activeDays.some(Boolean)) {
      Alert.alert('Required', 'Select at least one working day.');
      return;
    }
    setStep('services');
  }

  async function finish() {
    const validServices = services.filter(s => s.name.trim() && s.price);
    if (validServices.length === 0) {
      Alert.alert('Required', 'Add at least one service with a name and price.');
      return;
    }
    try {
      const barber = await saveBarber({
        name: name.trim(),
        shop_name: shopName.trim(),
        phone: phone.trim(),
        profile_photo_url: photoUri,
      });
      setBarber(barber);
      setCurrency(currency);

      await saveAvailability(
        activeDays.map((active, idx) => ({
          barber_id: barber.id,
          day_of_week: idx,
          start_time: startTime,
          end_time: endTime,
          is_active: active,
        }))
      );

      const created = [];
      for (const svc of validServices) {
        const s = await createService({
          barber_id: barber.id,
          name: svc.name.trim(),
          price: parseFloat(svc.price),
          duration_minutes: 30,
        });
        created.push(s);
      }
      setServices(created);

      // Attempt anonymous auth in background — non-blocking
      signInAnonymously().catch(() => {});

      onComplete();
    } catch {
      Alert.alert('Error', 'Something went wrong. Please try again.');
    }
  }

  if (step === 'profile') {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.heading}>Set up your profile</Text>
        <Text style={styles.sub}>Get started in under 15 minutes</Text>

        <TouchableOpacity style={styles.photoButton} onPress={pickPhoto}>
          {photoUri
            ? <Image source={{ uri: photoUri }} style={styles.photo} />
            : <Text style={styles.photoPlaceholder}>{'Add Photo\n(optional)'}</Text>
          }
        </TouchableOpacity>

        <Text style={styles.label}>Your Name *</Text>
        <TextInput style={styles.input} value={name} onChangeText={setName}
          placeholder="e.g. Marcus" placeholderTextColor={colors.textDim} />

        <Text style={styles.label}>Shop Name *</Text>
        <TextInput style={styles.input} value={shopName} onChangeText={setShopName}
          placeholder="e.g. Fresh Cutz" placeholderTextColor={colors.textDim} />

        <Text style={styles.label}>Phone Number *</Text>
        <TextInput style={styles.input} value={phone} onChangeText={setPhone}
          placeholder="e.g. 0300-1234567" placeholderTextColor={colors.textDim}
          keyboardType="phone-pad" />

        <Text style={styles.label}>Currency</Text>
        <View style={styles.currencyRow}>
          {CURRENCIES.map(c => (
            <TouchableOpacity
              key={c.code}
              style={[styles.currencyChip, currency === c.code && styles.currencyChipActive]}
              onPress={() => setCurrencyLocal(c.code)}
            >
              <Text style={[styles.currencyText, currency === c.code && styles.currencyTextActive]}>
                {c.symbol} {c.code}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity style={styles.primaryBtn} onPress={goProfile}>
          <Text style={styles.primaryBtnText}>Next: Working Hours</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  if (step === 'hours') {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={styles.heading}>Working Hours</Text>

        <Text style={styles.label}>Working Days</Text>
        <View style={styles.daysRow}>
          {DAYS.map((day, i) => (
            <TouchableOpacity
              key={day}
              style={[styles.dayBtn, activeDays[i] && styles.dayBtnActive]}
              onPress={() => {
                const next = [...activeDays];
                next[i] = !next[i];
                setActiveDays(next);
              }}
            >
              <Text style={[styles.dayLabel, activeDays[i] && styles.dayLabelActive]}>{day}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.label}>Start Time</Text>
        <TextInput style={styles.input} value={startTime} onChangeText={setStartTime}
          placeholder="09:00" placeholderTextColor={colors.textDim} />

        <Text style={styles.label}>End Time</Text>
        <TextInput style={styles.input} value={endTime} onChangeText={setEndTime}
          placeholder="18:00" placeholderTextColor={colors.textDim} />

        <TouchableOpacity style={styles.primaryBtn} onPress={goServices}>
          <Text style={styles.primaryBtnText}>Next: Services</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={styles.heading}>Your Services</Text>
      {services.map((svc, i) => (
        <View key={i} style={styles.serviceRow}>
          <TextInput
            style={[styles.input, { flex: 1 }]}
            value={svc.name}
            onChangeText={(v) => { const next = [...services]; next[i].name = v; setServicesList(next); }}
            placeholder="Service name"
            placeholderTextColor={colors.textDim}
          />
          <TextInput
            style={[styles.input, styles.priceInput]}
            value={svc.price}
            onChangeText={(v) => { const next = [...services]; next[i].price = v; setServicesList(next); }}
            placeholder="0"
            placeholderTextColor={colors.textDim}
            keyboardType="decimal-pad"
          />
        </View>
      ))}
      <TouchableOpacity style={styles.addRowBtn}
        onPress={() => setServicesList([...services, { name: '', price: '' }])}>
        <Text style={styles.addRowText}>+ Add Service</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.primaryBtn} onPress={finish}>
        <Text style={styles.primaryBtnText}>Start Using BarberApp</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingTop: 64, gap: spacing.sm },
  heading: { color: colors.text, fontSize: 28, fontWeight: '800', marginBottom: spacing.xs },
  sub: { color: colors.textMuted, fontSize: 14, marginBottom: spacing.lg },
  label: { color: colors.textMuted, fontSize: 13, marginTop: spacing.md, marginBottom: 4 },
  input: {
    backgroundColor: colors.surface, color: colors.text, padding: spacing.md,
    borderRadius: radius.md, fontSize: 16, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget,
  },
  primaryBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', marginTop: spacing.xl, minHeight: minTapTarget, justifyContent: 'center',
  },
  primaryBtnText: { color: '#000', fontWeight: '700', fontSize: 16 },
  photoButton: {
    width: 100, height: 100, borderRadius: 50, backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border, alignSelf: 'center',
    alignItems: 'center', justifyContent: 'center', marginBottom: spacing.md,
  },
  photo: { width: 100, height: 100, borderRadius: 50 },
  photoPlaceholder: { color: colors.textMuted, fontSize: 12, textAlign: 'center' },
  daysRow: { flexDirection: 'row', gap: spacing.xs, flexWrap: 'wrap' },
  dayBtn: {
    flex: 1, minWidth: 40, minHeight: minTapTarget, backgroundColor: colors.surface,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  dayBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '600' },
  dayLabelActive: { color: '#000' },
  serviceRow: { flexDirection: 'row', gap: spacing.sm },
  priceInput: { width: 88 },
  addRowBtn: { padding: spacing.sm, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center' },
  addRowText: { color: colors.primary, fontWeight: '600' },
  currencyRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  currencyChip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.xl,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
    minHeight: minTapTarget, justifyContent: 'center',
  },
  currencyChipActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  currencyText: { color: colors.textMuted, fontWeight: '600', fontSize: 13 },
  currencyTextActive: { color: colors.text },
});
