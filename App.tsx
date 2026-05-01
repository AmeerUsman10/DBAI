import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator, StyleSheet, AppState } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { initDb } from './src/database/schema';
import { getBarber } from './src/database/db';
import { flushSyncQueue, getPendingCount } from './src/database/sync';
import { useStore } from './src/store/useStore';
import { OnboardingScreen } from './src/screens/onboarding/OnboardingScreen';
import { RootNavigator } from './src/navigation/RootNavigator';
import { colors } from './src/theme/colors';

type AppPhase = 'loading' | 'onboarding' | 'main';

export default function App() {
  const [phase, setPhase] = useState<AppPhase>('loading');
  const setBarber = useStore((s) => s.setBarber);
  const setSyncStatus = useStore((s) => s.setSyncStatus);

  useEffect(() => {
    async function boot() {
      await initDb();
      const barber = await getBarber();
      if (barber) {
        setBarber(barber);
        setPhase('main');
      } else {
        setPhase('onboarding');
      }
    }
    boot();
  }, []);

  // Sync only after DB is ready — gated on phase
  useEffect(() => {
    if (phase === 'loading') return;

    async function trySync() {
      const pending = await getPendingCount();
      if (pending === 0) {
        setSyncStatus('synced');
        return;
      }
      setSyncStatus('pending');
      await flushSyncQueue();
      const remaining = await getPendingCount();
      setSyncStatus(remaining === 0 ? 'synced' : 'pending');
    }

    trySync();

    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') trySync();
    });
    return () => sub.remove();
  }, [phase]);

  if (phase === 'loading') {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <SafeAreaView style={styles.root} edges={['top']}>
          {phase === 'onboarding'
            ? <OnboardingScreen onComplete={() => setPhase('main')} />
            : <RootNavigator />
          }
        </SafeAreaView>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  splash: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' },
  root: { flex: 1, backgroundColor: colors.bg },
});
