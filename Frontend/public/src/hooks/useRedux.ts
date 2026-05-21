import { useAppDispatch, useAppSelector } from "@/lib/redux/store";
import { resetStore } from "@/lib/redux/store";
import { persistor } from "@/lib/redux/store";

export const useRedux = () => {
    const dispatch = useAppDispatch();
    const selector = useAppSelector;

    const resetReduxStore = () => {
        persistor.purge();
        dispatch(resetStore());
    };

    return {
        dispatch,
        selector,
        resetReduxStore,
    };
};
