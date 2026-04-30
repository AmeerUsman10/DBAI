import React, { useState, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Image, Alert } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useStore } from '../store/useStore';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import { createCaptureSession, updateCaptureSession, createPortfolioItem } from '../database/db';

type CaptureStep = 'before' | 'after' | 'review';

interface Props {
  appointmentId?: string;
  clientId?: string;
  onDone: () => void;
}

export function CaptureScreen({ appointmentId, clientId, onDone }: Props) {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('capture'));
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [step, setStep] = useState<CaptureStep>('before');
  const [beforeUri, setBeforeUri] = useState<string | null>(null);
  const [afterUri, setAfterUri] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [autoPublish, setAutoPublish] = useState(false);

  if (!permission) return null;

  if (!permission.granted) {
    return (
      <View style={styles.permContainer}>
        <Text style={styles.permText}>Camera access is needed for before/after captures.</Text>
        <TouchableOpacity style={styles.permBtn} onPress={requestPermission}>
          <Text style={styles.permBtnText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  async function capture() {
    if (!cameraRef.current || !barber) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.85 });
      if (!photo) return;

      if (step === 'before') {
        setBeforeUri(photo.uri);
        const session = await createCaptureSession({
          barber_id: barber.id,
          client_id: clientId,
          appointment_id: appointmentId,
          photo_before_url: photo.uri,
          paired: false,
          auto_published: false,
        });
        setSessionId(session.id);
        setStep('after');
      } else if (step === 'after') {
        setAfterUri(photo.uri);
        if (sessionId) {
          await updateCaptureSession(sessionId, {
            photo_after_url: photo.uri,
            paired: true,
            auto_published: autoPublish,
          });
          if (autoPublish) {
            await createPortfolioItem({
              barber_id: barber.id,
              client_id: clientId,
              photo_before_url: beforeUri ?? undefined,
              photo_after_url: photo.uri,
              style_tag: 'other',
              visibility: 'private',
            });
          }
        }
        setStep('review');
      }
    } catch {
      Alert.alert('Error', 'Failed to take photo. Please try again.');
    }
  }

  if (step === 'review') {
    return (
      <View style={styles.container}>
        <Text style={styles.reviewTitle}>Capture Complete</Text>
        <View style={styles.reviewRow}>
          {beforeUri && (
            <View style={styles.reviewCard}>
              <Text style={styles.reviewLabel}>Before</Text>
              <Image source={{ uri: beforeUri }} style={styles.reviewImage} resizeMode="cover" />
            </View>
          )}
          {afterUri && (
            <View style={styles.reviewCard}>
              <Text style={styles.reviewLabel}>After</Text>
              <Image source={{ uri: afterUri }} style={styles.reviewImage} resizeMode="cover" />
            </View>
          )}
        </View>
        <Text style={styles.savedText}>Saved to client record and portfolio</Text>

        {isAdvanced && (
          <View style={styles.advancedSection}>
            <View style={[styles.lockedFeature]}>
              <Text style={styles.lockedTitle}>Consistency Score</Text>
              <Text style={styles.lockedSub}>Available after 50 captures</Text>
            </View>
            <View style={styles.lockedFeature}>
              <Text style={styles.lockedTitle}>GPT Style Simulation</Text>
              <Text style={styles.lockedSub}>Coming in next update</Text>
            </View>
          </View>
        )}

        <TouchableOpacity style={styles.doneBtn} onPress={onDone}>
          <Text style={styles.doneBtnText}>Done</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.stepLabel}>{step === 'before' ? 'Step 1: Before Photo' : 'Step 2: After Photo'}</Text>
      <View style={styles.cameraContainer}>
        <CameraView ref={cameraRef} style={styles.camera} facing="back">
          {/* Face alignment oval guide */}
          <View style={styles.ovalGuide} />
        </CameraView>
      </View>

      {isAdvanced && (
        <TouchableOpacity
          style={styles.autoPublishToggle}
          onPress={() => setAutoPublish(v => !v)}
        >
          <Text style={styles.autoPublishText}>
            Auto-publish: {autoPublish ? 'ON' : 'OFF'}
          </Text>
        </TouchableOpacity>
      )}

      <TouchableOpacity style={styles.captureBtn} onPress={capture}>
        <View style={styles.captureBtnInner} />
      </TouchableOpacity>

      <TouchableOpacity style={styles.cancelCapture} onPress={onDone}>
        <Text style={styles.cancelCaptureText}>Cancel</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', alignItems: 'center' },
  permContainer: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: spacing.lg, gap: spacing.md },
  permText: { color: colors.text, textAlign: 'center', fontSize: 16 },
  permBtn: { backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md, minWidth: 200, alignItems: 'center' },
  permBtnText: { color: '#000', fontWeight: '700' },
  stepLabel: { color: '#fff', fontSize: 18, fontWeight: '700', marginTop: 48, marginBottom: spacing.md },
  cameraContainer: { width: '100%', flex: 1 },
  camera: { flex: 1 },
  ovalGuide: {
    position: 'absolute', top: '10%', left: '20%',
    width: '60%', height: '55%',
    borderRadius: 999, borderWidth: 2, borderColor: 'rgba(255,255,255,0.6)',
  },
  captureBtn: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: 'rgba(255,255,255,0.3)', alignItems: 'center',
    justifyContent: 'center', marginBottom: 40, marginTop: spacing.lg,
    borderWidth: 3, borderColor: '#fff',
  },
  captureBtnInner: {
    width: 56, height: 56, borderRadius: 28, backgroundColor: '#fff',
  },
  cancelCapture: { position: 'absolute', top: 48, right: 20, padding: spacing.sm },
  cancelCaptureText: { color: '#fff', fontSize: 15 },
  autoPublishToggle: {
    padding: spacing.sm, borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.primary, marginBottom: spacing.sm,
  },
  autoPublishText: { color: colors.primary, fontWeight: '600' },
  reviewTitle: { color: '#fff', fontSize: 22, fontWeight: '800', marginTop: 48, marginBottom: spacing.md },
  reviewRow: { flexDirection: 'row', gap: spacing.md, paddingHorizontal: spacing.md },
  reviewCard: { flex: 1, gap: spacing.xs },
  reviewLabel: { color: colors.textMuted, fontSize: 13, textAlign: 'center' },
  reviewImage: { width: '100%', aspectRatio: 1, borderRadius: radius.md },
  savedText: { color: colors.success, fontSize: 14, marginTop: spacing.md },
  advancedSection: { gap: spacing.sm, padding: spacing.md, width: '100%' },
  lockedFeature: {
    backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border, opacity: 0.6,
  },
  lockedTitle: { color: colors.text, fontWeight: '600' },
  lockedSub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  doneBtn: {
    backgroundColor: colors.primary, paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md, borderRadius: radius.md,
    marginTop: spacing.lg, minHeight: minTapTarget, justifyContent: 'center',
  },
  doneBtnText: { color: '#000', fontWeight: '700', fontSize: 16 },
});
