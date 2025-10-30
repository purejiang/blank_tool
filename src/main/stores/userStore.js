import Store from 'electron-store';
import { safeStorage } from 'electron';

const schema = {
    username: {
        type: 'string',
        default: ''
    },
    token: {
        type: 'string',
        default: ''
    },
    user_id: {
        type: 'string',
        default: ''
    },
    preferences: {
        type: 'object',
        properties: {
            notifications: { type: 'boolean', default: true },
            fontSize: { type: 'number', default: 14 },
            darkMode: { type: 'boolean', default: false }
        },
        default: {}
    }
};

const userStore = new Store({
    name: 'user-data',
    schema,
    encryptionKey: safeStorage.isEncryptionAvailable()
        ? safeStorage.encryptString('user-data-key')
        : undefined
});

// 安全存储敏感数据
userStore.setSecure = (key, value) => {
    if (safeStorage.isEncryptionAvailable()) {
        const encrypted = safeStorage.encryptString(value);
        userStore.set(key, encrypted.toString('latin1'));
    } else {
        userStore.set(key, value);
    }
};

userStore.getSecure = (key) => {
    const value = userStore.get(key);
    if (!value) return null;

    if (safeStorage.isEncryptionAvailable()) {
        const buffer = Buffer.from(value, 'latin1');
        return safeStorage.decryptString(buffer);
    }

    return value;
};

export default userStore;